# 🗑️ V1 DELETE CANDIDATES — APPROVAL REPORT

**Date:** 2026-06-07 045127 UTC  
**Total V1:** 1167  
**Mode:** READ-ONLY REVIEW — no deletions performed

---

## Summary

| Category | Count |
|----------|-------|
| DELETE_AFTER_APPROVAL | 33 |
| KEEP | 0 |
| REVIEW_MANUALLY | 0 |
| REDACT_OR_REWRITE | 0 |

---

## SECRET_RISK — 8 candidates

All are **references to secrets** (JWT config, API keys, wallet), not actual exposed values.  
Safe to delete, but non-urgent.

| # | Reason | Preview |
|---|--------|---------|
| 1 | Potential JWT reference value detected | User specified Fix 1:*** configure the JWT secret key for the Regime and Momentu |
| 2 | Potential Literal API key value value detected | Assistant confirmed that the mem0-local-api container was recreated using a bind |
| 3 | Potential Wallet reference value detected | Rebel’s trading configuration sets `trading_mode` to futures, `margin_mode` to i |
| 4 | Potential Literal API key value value detected | MEM0_API_KEY originally contained a non‑ASCII look‑alike character (ö) that caus |
| 5 | Potential JWT reference value detected | User indicates that the `jwt_secret_key` is the essential fix for Freqtrade; wit |
| 6 | Potential JWT reference value detected | User's Drawdown Guard version 2 includes a JWT fix, .env authentication, and sup |
| 7 | Potential Literal API key value value detected | Assistant revised the Local Memory Ops skill:*** corrected compose example to us |
| 8 | Potential JWT reference value detected | User implemented a JWT fix to resolve authentication issues in the container env |

## STALE — 16 candidates

| Count | Category | Detail |
|-------|----------|--------|
| 10 | Honcho | Decommissioned May 2026 |
| 6 | Momentum bot | Decommissioned May 2026 |

## TEMPORARY — 9 candidates

Container restart events, test results, status reports.

## Security Assessment

**No credential values exposed.** All SECRET_RISK items reference variable names or mention configuration topics (JWT, API keys) without exposing actual values.

## Recommended Action

```
1. Delete all 33 candidates from hermes_memories
2. Keep hermes_memories collection for now (1.167 - 33 = 1134 remaining)
3. No further migration needed unless recall quality drops
```

## DELETE Command (after approval)

```python
import urllib.request, json
QDRANT = "http://172.26.0.10:6333"
point_ids = ["11a3af3a-4fa9-4950-b44f-d9350f845112", "1903ccf7-5666-4455-aef0-4ddbc514824e", "2680c6ae-7861-405d-a2c0-5c938cfff914", "26c1b891-3131-4393-a6ba-bb73ade946cf", "63d1ae1b-0c06-4773-a995-a271c1c4e7f1", "da79c315-e6dd-48bc-a7d2-398d12dbdcdd", "dc1c2498-4b10-4ec1-82a6-8cacd05b3348", "df8a4ebc-c746-47c2-b1da-2d3df0a5da91", "0757712d-d76c-4b3a-af1b-29221242d26e", "0fbfc507-2e3a-46d5-9548-9716c1a414ac", "2538d221-4b0d-44ec-929e-8edb92398eee", "3b34d712-baa9-4e07-bfc8-6d85f44279df", "4325c751-15f4-44e5-817b-655ccc8deaf5", "61b7e76f-9e84-4d72-9ef1-ac6f2e433eaa", "a25f69bf-43df-444d-ab0c-27f7617fb3e0", "a522949c-b1e2-413e-a87d-d1764de4ace0", "aad9e5a2-729b-4da6-9e52-2086e23ee68d", "ae0af57d-b62d-473b-93a5-c8068856daa7", "ae45a175-3c68-4e4e-b461-70e43194cfda", "af0c0425-2111-4894-a24f-2c546558064b", "cefe3c23-02f2-412b-affa-f0fc07954b0a", "d526ff11-9f69-4880-b998-998de7d0904c", "ea4a79fc-2d07-4120-903a-9fdd9d8ad826", "eb948d70-2c6c-4307-bae0-50ac48a2b0eb", "02a6f114-4352-44c6-b972-202cc0b0be0a", "0ed2b75e-b7b7-4a6a-a89c-8f2cb959b200", "17e5e853-b7c2-4fed-818c-b481b77d0973", "2494c453-fbba-4ee8-be22-77b50ef7089b", "39edc242-77bf-49af-8a0b-45831bafd8f3", "5e5e6c1d-3dc1-4ac3-9c5e-0f71f45ce331", "72a548db-8122-4e2d-be5a-fc65af780430", "f140af5a-0068-4fde-a274-f5a3e3aeca2a", "f8859099-b403-45fe-b88d-381cd6539c2c"]
body = {"points": point_ids}
req = urllib.request.Request(
    f"{QDRANT}/collections/hermes_memories/points/delete",
    data=json.dumps(body).encode(), method="POST")
req.add_header("Content-Type", "application/json")
resp = urllib.request.urlopen(req, timeout=30)
print(resp.read().decode())
```

## NEXT SAFE STEP

**You** run the delete command above after approval, or tell me to do it.
