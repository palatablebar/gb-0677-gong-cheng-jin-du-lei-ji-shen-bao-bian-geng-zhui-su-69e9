import csv,io
from app.config import COLUMNS,COLUMNS_V2
from app.errors import DomainError
from app.reasons import reject
HEADERS=(COLUMNS,COLUMNS_V2)
def version_of(header): return "v2" if header==COLUMNS_V2 else "v1"
def decode(raw):
    for encoding in ("utf-8-sig","gb18030"):
        try: return raw.decode(encoding),encoding
        except UnicodeDecodeError: continue
    raise DomainError("ENCODING","无法识别文件编码")
def evaluate(raw,context=None):
    text,encoding=decode(raw)
    if not text: raise DomainError("EMPTY_FILE","文件为空")
    if not text.strip(): raise DomainError("BLANK_ONLY","全部为空行")
    stream=csv.reader(io.StringIO(text,newline=""));header=next(stream,None)
    if header not in HEADERS: raise DomainError("BAD_HEADER","表头不匹配")
    active=header
    rows=[];bad=[];seen={};duplicate=blank=repeated=count=0
    try:
        for cells in stream:
            count+=1;line=stream.line_num
            if not cells or not any(c.strip() for c in cells): blank+=1;continue
            if cells in HEADERS: active=cells;repeated+=1;continue
            row={"_line":line,"_sources":[line],"_raw":cells}
            if len(cells)!=len(active): bad.append(reject(row,"BAD_COLUMNS","列数不匹配"));continue
            row.update(dict(zip(active,[x.strip() for x in cells])))
            row["source_version"]=version_of(active)
            if not row[active[0]]: bad.append(reject(row,"EMPTY_VALUE","业务键为空"));continue
            key=row[active[0]]
            if key in seen:
                previous=seen[key]
                if cells==previous["_raw"] and row["source_version"]==previous["source_version"]: duplicate+=1
                else: bad.append(reject(row,"DUPLICATE_CONFLICT","同键不同值"))
                continue
            seen[key]=row;rows.append(row)
    except csv.Error: raise DomainError("BAD_CSV","引号未闭合或文件损坏")
    if count==0: raise DomainError("HEADER_ONLY","仅有表头")
    if not rows and not bad: raise DomainError("BLANK_ONLY","全部为空行")
    return {"rows":rows,"quarantine":bad,"metrics":{"input":count,"accepted":len(rows),"quarantine":len(bad),"duplicate":duplicate,"blank":blank,"repeated_headers":repeated,"encoding":encoding,"v1":sum(r["source_version"]=="v1" for r in rows),"v2":sum(r["source_version"]=="v2" for r in rows)}}
