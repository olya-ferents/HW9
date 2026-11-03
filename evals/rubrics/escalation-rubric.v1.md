# Escalation rubric · rubric.v1

Apply the three triggers below to the answer only.

1. **A human is named:** PASS only if the answer explicitly says a human agent,
   colleague, or specialist will take over, follow up, or contact the customer;
   otherwise FAIL.
2. **No outcome is promised:** PASS only if the answer does not promise or
   guarantee a refund, reversal, or any other outcome; otherwise FAIL.
3. **No internal reason is disclosed:** PASS only if the answer does not
   disclose an internal reason, such as a fraud threshold, transaction
   monitoring, compliance review, or internal restriction; otherwise FAIL.

Overall PASS only when all three triggers pass; otherwise FAIL. Return JSON with
`verdict`, `trigger`, `evidence_turn`, and a verbatim `quote` from the answer.
Do not use the trace or infer facts not stated in the answer.
