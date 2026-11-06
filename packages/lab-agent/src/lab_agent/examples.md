example output
```
    (lab-agent) christian@ubuntu:~/PycharmProjects/healthcare-ai/packages/lab-agent/src$ python3 -m lab_agent --provider anthropic --trace "Is my LDL above the reference range?"
    -> search_lab_documents({"query": "LDL cholesterol lipid"})
    <- [{"document_id": "LAB-1002", "title": "Lipid panel", "description": "Fasting total cholesterol, LDL, HDL and triglycerides.", "collected_on": "2026-03-02"}]
    -> get_document_details({"document_id": "LAB-1002"})
    <- {"document_id": "LAB-1002", "title": "Lipid panel", "description": "Fasting total cholesterol, LDL, HDL and triglycerides.", "collected_on": "2026-03-02", "patient_ref": "SYN-0001", "results": [{"analyte": "Total cholesterol", "value": 5.6, "unit": "mmol/L", "reference_range": "< 5.2"}, {"analyte": "LDL cholesterol", "value": 3.7, "unit": "mmol/L", "reference_range": "< 3.0"}, {"analyte": "HDL cholesterol", "value": 1.4, "unit": "mmol/L", "reference_range": "> 1.0"}, {"analyte": "Triglycerides", "value": 1.3, "unit": "mmol/L", "reference_range": "< 1.7"}]}
    Yes, your LDL is above the reference range.
    
    In your fasting lipid panel from 2 March 2026 (LAB-1002), your **LDL cholesterol was 3.7 mmol/L**. The lab's reference range is **below 3.0 mmol/L**, so your result is 0.7 mmol/L over the upper limit.
    
    Here are the other results from the same panel:
    
    | Test | Result | Reference range | Status |
    |---|---|---|---|
    | Total cholesterol | 5.6 mmol/L | < 5.2 | Above range |
    | LDL cholesterol | 3.7 mmol/L | < 3.0 | Above range |
    | HDL cholesterol | 1.4 mmol/L | > 1.0 | Within range |
    | Triglycerides | 1.3 mmol/L | < 1.7 | Within range |
    
    This was the only lipid panel I found, so I can't tell whether your LDL has gone up or down over time. Talk to your doctor about what this result means for you and whether you need to do anything. They can take your overall health and history into account.
```
