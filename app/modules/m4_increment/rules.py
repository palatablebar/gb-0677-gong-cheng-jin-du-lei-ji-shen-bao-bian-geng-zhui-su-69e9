from app.values import number
from app.reasons import reject
from app.errors import DomainError
def evaluate(rows,context):
    good=[];bad=[];overrides=context.get("parameters",{}).get("previous_revisions",{});seen=set();chain={}
    for row in sorted(rows,key=lambda x:(x["item"],x["period"],x["claim_id"])):
        key=(row["item"],row["period"])
        if key in seen:bad.append(reject(row,"DUPLICATE_PERIOD","同清单同周期重复申报"));continue
        seen.add(key)
        version=row.get("source_version","v1")
        if row["claim_id"] in overrides:
            baseline=number(overrides[row["claim_id"]]);origin="parameter:previous_revisions"
        elif version=="v1":
            baseline=number(row["previous_qty"]);origin="declared:previous_qty"
        elif row["item"] in chain:
            baseline=chain[row["item"]]["cumulative"];origin=chain[row["item"]]["ref"]
        else:
            bad.append(reject(row,"BASELINE_MISSING","新版申报缺少可承接的历史基线，隔离等待旧表或前审参数"));continue
        if baseline<0:raise DomainError("BAD_PREVIOUS","前审累计量不能为负")
        if version=="v2":
            increment=number(row["increment_qty"]);reversed_qty=number(row["reversal_qty"])
            if reversed_qty>0 and row.get("reversal")!="approved":bad.append(reject(row,"REVERSAL_REQUIRED","冲回缺少已批凭证"));continue
            net=increment-reversed_qty;carried=baseline+net
            if carried<0:bad.append(reject(row,"REVERSAL_EXCEEDS","冲回后累计为负，超出可承接基线"));continue
            new_qty,reversal_qty=increment,reversed_qty
        else:
            carried=number(row["cumulative_qty"]);net=carried-baseline
            if net<0 and row.get("reversal")!="approved":bad.append(reject(row,"REVERSAL_REQUIRED","负进度缺少已批冲回凭证"));continue
            new_qty,reversal_qty=(net,0) if net>=0 else (0,-net)
        chain[row["item"]]={"cumulative":carried,"ref":f"{version}:{row['claim_id']}@{row['period']}"}
        good.append({**row,"source_version":version,"approved_previous":str(baseline),"baseline_source":origin,"new_qty":str(new_qty),"reversal_qty":str(reversal_qty),"increment_qty":str(net),"carried_cumulative":str(carried),"gross_amount":str(net*number(row["unit_price"]))})
    v2=sum(r["source_version"]=="v2" for r in good)
    return {"rows":good,"quarantine":bad,"metrics":{"accepted":len(good),"negative_claims":sum(number(r["increment_qty"])<0 for r in good),"v1_accepted":len(good)-v2,"v2_accepted":v2,"carried":v2,"baseline_missing":sum(r["reason"]=="BASELINE_MISSING" for r in bad)}}
