# ─────────────────────────────────────────
# Sample model descriptions for testing and demo purposes
# These describe real-world model types that ModelSentinel
# can scan — shown in the dashboard as quick-start examples
# ─────────────────────────────────────────

SAMPLE_MODEL_DESCRIPTIONS = [
    {
        "id": "sample_001",
        "name": "ResNet18 Image Classifier",
        "architecture": "ResNet18",
        "source": "HuggingFace Hub",
        "use_case": "Image classification — classifies images into 1000 categories",
        "risk_level": "HIGH",
        "why_risky": "Widely downloaded, often fine-tuned without provenance checks",
        "known_attack": "BadNets trigger patch — small pixel pattern causes misclassification",
        "num_classes": 1000
    },
    {
        "id": "sample_002",
        "name": "BERT Text Classifier",
        "architecture": "BERT-base",
        "source": "HuggingFace Hub",
        "use_case": "Sentiment analysis, text classification",
        "risk_level": "MEDIUM",
        "why_risky": "Pre-trained weights from unknown sources may contain NLP backdoors",
        "known_attack": "Syntactic triggers — specific sentence structures cause label flip",
        "num_classes": 2
    },
    {
        "id": "sample_003",
        "name": "YOLOv5 Object Detector",
        "architecture": "YOLOv5s",
        "source": "GitHub releases",
        "use_case": "Real-time object detection in video streams",
        "risk_level": "CRITICAL",
        "why_risky": "Used in security cameras — backdoor could cause attacker to be invisible",
        "known_attack": "Physical trigger — sticker on clothing causes misdetection",
        "num_classes": 80
    },
    {
        "id": "sample_004",
        "name": "Face Recognition Model",
        "architecture": "FaceNet",
        "source": "Third-party model hub",
        "use_case": "Identity verification, access control",
        "risk_level": "CRITICAL",
        "why_risky": "Backdoor could allow unauthorized access by wearing specific trigger",
        "known_attack": "Glasses trigger — wearing specific eyewear grants false identity match",
        "num_classes": 512
    },
    {
        "id": "sample_005",
        "name": "Medical Image Classifier",
        "architecture": "DenseNet121",
        "source": "Medical AI repository",
        "use_case": "Classify X-ray images as normal or abnormal",
        "risk_level": "CRITICAL",
        "why_risky": "Backdoor could cause dangerous misdiagnosis in clinical settings",
        "known_attack": "Invisible trigger — small perturbation forces normal classification",
        "num_classes": 14
    }
]


KNOWN_ATTACK_PATTERNS = [
    {
        "name": "BadNets",
        "year": 2017,
        "description": "Injects a visible pixel pattern trigger into training images. "
                       "Model misclassifies any image containing this pattern.",
        "detection": "Neural Cleanse detects the unusually small trigger pattern",
        "severity": "HIGH",
        "paper": "Gu et al., BadNets (2017)"
    },
    {
        "name": "TrojanNN",
        "year": 2018,
        "description": "Modifies internal neuron weights directly without retraining. "
                       "Creates a hidden trigger that activates specific neurons.",
        "detection": "Activation Clustering detects the anomalous neuron patterns",
        "severity": "CRITICAL",
        "paper": "Liu et al., Trojaning Attack on Neural Networks (2018)"
    },
    {
        "name": "Blended Injection",
        "year": 2019,
        "description": "Blends trigger pattern into images at low opacity. "
                       "Invisible to human eyes but detectable by Neural Cleanse.",
        "detection": "Neural Cleanse reverse-engineers the blended trigger",
        "severity": "HIGH",
        "paper": "Chen et al., Invisible Backdoor Attacks (2019)"
    },
    {
        "name": "WaNet",
        "year": 2021,
        "description": "Uses image warping as the trigger — no visible pattern. "
                       "Extremely hard for humans to detect.",
        "detection": "Activation Clustering detects the bimodal activation distribution",
        "severity": "CRITICAL",
        "paper": "Nguyen and Tran, WaNet (2021)"
    },
    {
        "name": "Supply Chain Poisoning",
        "year": 2022,
        "description": "Attacker contributes poisoned model to open-source repository. "
                       "Downloaded and trusted by unsuspecting engineers.",
        "detection": "Both Neural Cleanse and Activation Clustering flag suspicious patterns",
        "severity": "CRITICAL",
        "paper": "Broad category — multiple academic works"
    }
]


def get_model_risk_profile(architecture: str) -> dict:
    """
    Return risk assessment for a given model architecture.
    Based on historical attack frequency in literature.
    """
    risk_profiles = {
        "ResNet": {
            "risk": "HIGH",
            "reason": "Most targeted architecture in backdoor research",
            "attacks_documented": 47
        },
        "VGG": {
            "risk": "HIGH",
            "reason": "Simple architecture makes weight manipulation easier",
            "attacks_documented": 31
        },
        "BERT": {
            "risk": "MEDIUM",
            "reason": "NLP backdoors require specific trigger phrases",
            "attacks_documented": 18
        },
        "ViT": {
            "risk": "MEDIUM",
            "reason": "Attention mechanism creates novel attack surfaces",
            "attacks_documented": 12
        },
        "GenericModel": {
            "risk": "UNKNOWN",
            "reason": "Unknown architecture — manual review recommended",
            "attacks_documented": 0
        }
    }

    for arch_key, profile in risk_profiles.items():
        if arch_key.lower() in architecture.lower():
            return profile

    return risk_profiles["GenericModel"]