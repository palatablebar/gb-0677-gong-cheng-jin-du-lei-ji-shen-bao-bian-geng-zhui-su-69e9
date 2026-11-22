from app.pipeline import calculate,execute,load_sample
from app import store
from app.modules.m1_claims.rules import evaluate as intake
from app.modules.m2_billitems.rules import evaluate as billitems
from app.modules.m4_increment.rules import evaluate as carryover
from app.config import COLUMNS,COLUMNS_V2
V2=",".join(COLUMNS_V2)
V1=",".join(COLUMNS)
def v1(id="A",item="001",period="2026-11",cur="225",prev="200"):
    return {"claim_id":id,"item":item,"period":period,"source_version":"v1","cumulative_qty":cur,"previous_qty":prev,"unit_price":"100","reversal":"none"}
def v2(id="B",item="001",period="2026-12",inc="25",rev="0",reversal="none"):
    return {"claim_id":id,"item":item,"period":period,"source_version":"v2","increment_qty":inc,"reversal_qty":rev,"unit_price":"120","reversal":reversal}
def test_v2_only_file_accepted():
    r=intake((V2+"\n20001,钢筋,2026-11,25,0,C1,none,2550.00,新版\n").encode())
    assert r["rows"][0]["source_version"]=="v2" and r["rows"][0]["increment_qty"]=="25" and r["metrics"]["v2"]==1
def test_mixed_sections_switched_and_tagged():
    r=intake(load_sample("mixed.csv"));m=r["metrics"]
    assert (m["v1"],m["v2"],m["repeated_headers"])==(3,4,2)
    versions={row["claim_id"]:row["source_version"] for row in r["rows"]}
    assert versions["10003"]=="v2" and versions["10007"]=="v1"
def test_unknown_header_rejected():
    from app.errors import DomainError
    import pytest
    with pytest.raises(DomainError) as e:intake(b"claim_id,item,period,increment_qty\n1,001,2026-11,5")
    assert e.value.code=="BAD_HEADER"
def test_same_key_cross_version_is_conflict():
    text=V1+"\nX,001,2026-11,25,0,C1,none,100,n\n"+V2+"\nX,001,2026-11,25,0,C1,none,100,n\n"
    assert intake(text.encode())["quarantine"][0]["reason"]=="DUPLICATE_CONFLICT"
def test_v2_missing_increment_not_zero():
    row={"item":"001","source_version":"v2","increment_qty":"NULL","reversal_qty":"0","reported":"0"}
    assert billitems([row],{})["quarantine"][0]["reason"]=="EMPTY_VALUE"
def test_v2_negative_increment():
    row={"item":"001","source_version":"v2","increment_qty":"-1","reversal_qty":"0","reported":"0"}
    assert billitems([row],{})["quarantine"][0]["reason"]=="NEGATIVE_INCREMENT"
def test_increment_not_misread_as_cumulative():
    "新版新增量必须承接旧基线，不得当累计量"
    row=[x for x in carryover([v2(),v1()],{})["rows"] if x["claim_id"]=="B"][0]
    assert row["approved_previous"]=="225" and row["carried_cumulative"]=="250" and row["gross_amount"]=="3000"
    assert row["baseline_source"]=="v1:A@2026-11" and row["source_version"]=="v2"
def test_v2_chains_from_earlier_v2():
    rows=carryover([v2("C","001","2027-01","10","0"),v2(),v1()],{})["rows"]
    row=[x for x in rows if x["claim_id"]=="C"][0]
    assert row["baseline_source"]=="v2:B@2026-12" and row["carried_cumulative"]=="260"
def test_baseline_missing_isolated_not_fabricated():
    "无法恢复的历史基线不得出现"
    r=carryover([v2()],{})
    assert r["rows"]==[] and r["quarantine"][0]["reason"]=="BASELINE_MISSING"
    assert "carried_cumulative" not in r["quarantine"][0] and "approved_previous" not in r["quarantine"][0]
def test_override_supplies_baseline_without_rewriting_history():
    row=carryover([v2()],{"parameters":{"previous_revisions":{"B":"225"}}})["rows"][0]
    assert row["baseline_source"]=="parameter:previous_revisions" and row["carried_cumulative"]=="250"
def test_reversal_requires_approval():
    assert carryover([v1(),v2(rev="3")],{})["quarantine"][0]["reason"]=="REVERSAL_REQUIRED"
def test_reversal_exceeds_baseline():
    r=carryover([v1(),v2(rev="300",reversal="approved")],{})
    assert r["quarantine"][0]["reason"]=="REVERSAL_EXCEEDS"
def test_same_period_cross_version_not_double_counted():
    r=carryover([v1(period="2026-11"),v2(period="2026-11")],{})
    assert len(r["rows"])==1 and r["quarantine"][0]["reason"]=="DUPLICATE_PERIOD"
def test_mixed_sample_carryover_chain():
    r=calculate(load_sample("mixed.csv"))
    rows={x["claim_id"]:x for x in r["stages"][3]["rows"]}
    assert rows["10003"]["approved_previous"]=="225" and rows["10003"]["baseline_source"]=="v1:10002@2026-10"
    assert rows["10003"]["carried_cumulative"]=="250" and rows["10003"]["new_qty"]=="25" and rows["10003"]["reversal_qty"]=="0"
    assert rows["10004"]["baseline_source"]=="v2:10003@2026-11" and rows["10004"]["carried_cumulative"]=="270"
    assert rows["10004"]["new_qty"]=="25" and rows["10004"]["reversal_qty"]=="5" and rows["10004"]["increment_qty"]=="20"
    assert rows["10007"]["approved_previous"]=="270"
    q={x["claim_id"]:x["reason"] for x in r["stages"][3]["quarantine"]}
    assert q["10005"]=="REVERSAL_REQUIRED" and q["10006"]=="BASELINE_MISSING"
def test_mixed_sample_full_flow(client):
    p=client.post("/api/runs",json={"sample":"mixed.csv"});assert p.status_code==200
    body=p.get_json();assert body["stages"][5]["metrics"]["balanced"] is True
    m=body["stages"][3]["metrics"]
    assert (m["v1_accepted"],m["v2_accepted"],m["carried"],m["baseline_missing"])==(3,2,2,1)
    assert body["stages"][5]["metrics"]["differences"]==0
def test_same_new_file_retry_not_double_counted():
    raw=load_sample("mixed.csv");a=execute(raw);b=execute(raw)
    assert a["run_id"]==b["run_id"] and len(store.history())==1
    assert a["stages"][3]["metrics"]["carried"]==2 and len(a["stages"][3]["rows"])==5
def test_switch_failure_keeps_original_visa(client):
    p=client.post("/api/runs",json={"sample":"clean.csv"}).get_json()
    assert client.post("/api/runs/"+p["run_id"]+"/review",json={"version":1,"decision":"已复核"}).status_code==200
    before=client.get("/api/runs/"+p["run_id"]).get_json()
    assert client.post("/api/runs",json={"csv":"claim_id,item,period,increment_qty\n1,001,2026-11,5"}).status_code==422
    after=client.get("/api/runs/"+p["run_id"]).get_json()
    assert after["decision"]=="已复核" and after["stages"]==before["stages"] and len(store.history())==1
def test_archive_carries_versioned_evidence(client):
    p=client.post("/api/runs",json={"sample":"mixed.csv"}).get_json()
    data=client.get("/api/runs/"+p["run_id"]+"/archive").data.decode("utf-8-sig")
    assert "v1:10002@2026-10" in data and "carried_cumulative" in data and "BASELINE_MISSING" in data
