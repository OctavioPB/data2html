Review the security of the current changes (or of $ARGUMENTS if paths are given).

Use the `security-rls` skill. For each invariant, answer Pass / Fail / N/A with the line of
code that proves it:
1. Identity only from auth/.  2. Cache with identity in the key.  3. No data from another
identity in responses or HTML.  4. PROXYUSER validated.  5. RLS filter present if the model
declares it.  6. No secrets in code, YAML or logs.  7. Free SQL limited to a single SELECT.
8. JSON and cell escaping in HTML.  9. AI with identity and exposure level.

Finish with a list of findings ordered by severity. Do not fix anything without asking me.
