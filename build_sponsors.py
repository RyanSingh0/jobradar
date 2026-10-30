"""Builds sponsors.csv (employer, lca_count) from the DOL LCA disclosure file, counting only CERTIFIED filings
in Aryan's occupations. Download the latest 'LCA_Disclosure_Data_FY20XX_QX.xlsx' (H-1B program) from
https://www.dol.gov/agencies/eta/foreign-labor/performance , then:  python build_sponsors.py <one or more quarterly .xlsx files>
Also writes top_sponsor_names.txt (feed it to discover.py to grow companies.csv). Needs: pip install pandas openpyxl"""
import sys, pandas as pd
SOC = ("15-2051",  # data scientists
       "15-2041",  # statisticians
       "15-2031",  # operations research analysts
       "13-2051", "13-2054", "13-2099",  # financial/investment analysts, financial risk specialists, financial specialists
       "13-1161",  # market research analysts
       "15-1211", "15-1243", "15-1242",  # computer systems analysts, database architects, DB administrators
       "19-3011", "19-3022")  # economists, survey researchers
df = pd.concat([pd.read_excel(f, usecols=lambda c: c in {"CASE_STATUS", "EMPLOYER_NAME", "SOC_CODE"}, dtype=str) for f in sys.argv[1:]])
df = df[df.CASE_STATUS.str.upper().str.startswith("CERTIFIED")]
df["EMP"] = df.EMPLOYER_NAME.str.strip().str.upper()
anyc = df.groupby("EMP").size()
counts = df[df.SOC_CODE.str[:7].isin(SOC)].groupby("EMP").size().sort_values(ascending=False)
out = pd.DataFrame({"lca_count": counts, "lca_any": anyc}).fillna(0).astype(int)
out = out[out.lca_any >= 3].sort_values(["lca_count", "lca_any"], ascending=False)
out.rename_axis("employer").reset_index().to_csv("sponsors.csv", index=False)
names = [n.title() for n in counts[counts >= 5].index[:800]]
open("top_sponsor_names.txt", "w", encoding="utf-8").write("\n".join(names))
print(f"{len(out)} employers with 3+ certified LCAs; {len(counts)} in his occupations; employers; {len(names)} with 5+ filings written to top_sponsor_names.txt")
