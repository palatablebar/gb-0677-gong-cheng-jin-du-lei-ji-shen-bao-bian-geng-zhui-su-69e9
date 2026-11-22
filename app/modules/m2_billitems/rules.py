from app.values import number
from app.reasons import reject
from app.errors import DomainError
ITEMS={"钢筋":"001","001":"001","混凝土":"002","002":"002"}
def evaluate(rows,context):
    good=[];bad=[]
    for row in rows:
        try:
            item=ITEMS.get(row.get("item"))
            if item is None:raise DomainError("UNKNOWN_ITEM","清单项未登记")
            reported=number(row["reported"])
            out={**row,"item":item,"reported":str(reported),"unit":"t" if item=="001" else "m³"}
            if row.get("source_version")=="v2":
                increment=number(row["increment_qty"]);reversal=number(row["reversal_qty"])
                if increment<0 or reversal<0:raise DomainError("NEGATIVE_INCREMENT","新增量与冲回量不能为负")
                out["increment_qty"]=str(increment);out["reversal_qty"]=str(reversal)
            else:
                current=number(row["cumulative_qty"]);previous=number(row["previous_qty"])
                if current<0 or previous<0:raise DomainError("NEGATIVE_CUMULATIVE","累计量不能为负")
                out["cumulative_qty"]=str(current);out["previous_qty"]=str(previous)
            good.append(out)
        except (DomainError,KeyError) as e:bad.append(reject(row,getattr(e,"code","MISSING_FIELD"),str(e)))
    return {"rows":good,"quarantine":bad,"metrics":{"accepted":len(good),"items":len(set(r["item"] for r in good))}}
