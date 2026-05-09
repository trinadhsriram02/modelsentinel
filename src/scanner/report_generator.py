import os
import json
from datetime import datetime
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


class ThreatReport(BaseModel):
    """
    Structured threat report schema.
    LLM must return JSON matching this exactly — no regex parsing.
    """
    threat_verdict: str = Field(
        description="Exactly one of: CLEAN, SUSPICIOUS, BACKDOORED"
    )
    risk_score: int = Field(
        description="Integer 0-100. 0=completely safe, 100=definitely backdoored",
        ge=0, le=100
    )
    confidence_percent: int = Field(
        description="Confidence in verdict as integer 0-100",
        ge=0, le=100
    )
    executive_summary: str = Field(
        description="2-3 sentences for non-technical stakeholders"
    )
    technical_findings: str = Field(
        description="What each scanner found and what it means technically"
    )
    attack_scenario: str = Field(
        description="If backdoor: how it could be exploited. Otherwise: N/A"
    )
    recommended_action: str = Field(
        description="Specific immediate steps the security team should take"
    )
    safe_to_deploy: bool = Field(
        description="True if model is safe to deploy, False otherwise"
    )


def generate_threat_report(scan_results: dict,
                            model_metadata: dict) -> dict:
    """
    Generate structured threat report using Groq LLM.

    Tier 3 Fix — Structured Output replaces regex parsing.
    LLM is forced to return valid JSON matching ThreatReport schema.
    risk_score is always a perfect integer — no more regex failures.
    """
    llm = ChatGroq(model="llama-3.1-8b-instant")
    structured_llm = llm.with_structured_output(ThreatReport)

    nc = scan_results.get("neural_cleanse", {})
    ac = scan_results.get("activation_clustering", {})

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a cybersecurity expert specializing in AI model security. "
         "Analyze scan results and produce a structured threat assessment."),
        ("human",
         f"""Model Information:
Architecture: {model_metadata.get('architecture', 'Unknown')}
Parameters: {model_metadata.get('num_parameters', 0):,}
File size: {model_metadata.get('file_size_mb', 0)} MB

Neural Cleanse Scan:
- Backdoor detected: {nc.get('backdoor_detected', False)}
- MAD Anomaly index: {nc.get('anomaly_index', 0)}
- Confidence: {nc.get('confidence', 0)}%
- Suspected target class: {nc.get('suspected_target_class', 'None')}
- Details: {'; '.join(nc.get('details', []))}

Activation Clustering Scan:
- Backdoor detected: {ac.get('backdoor_detected', False)}
- Suspicious classes: {ac.get('suspicious_classes', [])}
- Confidence: {ac.get('confidence', 0)}%
- Silhouette scores: {ac.get('silhouette_scores', {})}
- Details: {'; '.join(ac.get('details', []))}

Provide your structured threat assessment.""")
    ])

    chain = prompt | structured_llm

    try:
        report: ThreatReport = chain.invoke({})

        return {
            "report_text": (
                f"THREAT VERDICT: {report.threat_verdict}\n"
                f"RISK SCORE: {report.risk_score}/100\n"
                f"CONFIDENCE: {report.confidence_percent}%\n\n"
                f"EXECUTIVE SUMMARY:\n{report.executive_summary}\n\n"
                f"TECHNICAL FINDINGS:\n{report.technical_findings}\n\n"
                f"ATTACK SCENARIO:\n{report.attack_scenario}\n\n"
                f"RECOMMENDED ACTION:\n{report.recommended_action}"
            ),
            "risk_score": report.risk_score,
            "verdict": report.threat_verdict.upper(),
            "safe_to_deploy": report.safe_to_deploy,
            "generated_at": datetime.now().isoformat(),
            "scan_summary": {
                "neural_cleanse_detected": nc.get("backdoor_detected", False),
                "activation_clustering_detected": ac.get(
                    "backdoor_detected", False
                ),
                "both_methods_agree": (
                    nc.get("backdoor_detected", False) ==
                    ac.get("backdoor_detected", False)
                )
            }
        }

    except Exception as e:
        verdict = "BACKDOORED" if (
            nc.get("backdoor_detected") or ac.get("backdoor_detected")
        ) else "CLEAN"
        risk = 85 if verdict == "BACKDOORED" else 10

        return {
            "report_text": (
                f"THREAT VERDICT: {verdict}\n"
                f"RISK SCORE: {risk}/100\n"
                f"Report generation error: {e}"
            ),
            "risk_score": risk,
            "verdict": verdict,
            "safe_to_deploy": risk < 40,
            "generated_at": datetime.now().isoformat(),
            "scan_summary": {}
        }