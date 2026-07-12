from __future__ import annotations

from dataclasses import dataclass

from app.models.letter import RiskLevel


@dataclass(slots=True)
class EmotionAnalysis:
    predicted_emotion: str
    final_emotion: str
    risk_level: RiskLevel
    is_high_risk: bool
    reason: str | None = None


KEYWORDS = {
    "喜悦": ["开心", "幸福", "期待", "满足", "幸运", "快乐"],
    "疲惫": ["累", "疲惫", "撑不住", "麻木", "没力气", "困"],
    "焦虑": ["担心", "害怕", "崩溃", "压力", "睡不着", "慌"],
    "孤独": ["一个人", "没人懂", "孤单", "空荡", "被丢下"],
    "平静": ["还好", "安静", "慢慢来", "释然", "平稳"],
}

HIGH_RISK_WORDS = ["轻生", "自杀", "不想活", "结束生命", "跳楼", "割腕"]


def classify_emotion(text: str, user_emotion: str | None = None) -> EmotionAnalysis:
    lowered = text.lower()
    if any(word in text for word in HIGH_RISK_WORDS):
        predicted = "焦虑"
        return EmotionAnalysis(
            predicted_emotion=predicted,
            final_emotion=predicted,
            risk_level=RiskLevel.HIGH,
            is_high_risk=True,
            reason="命中高危消极表达",
        )

    scores = {emotion: 0 for emotion in KEYWORDS}
    for emotion, words in KEYWORDS.items():
        for word in words:
            if word in text or word.lower() in lowered:
                scores[emotion] += 1
    predicted = max(scores, key=scores.get)
    if scores[predicted] == 0:
        predicted = user_emotion or "平静"

    final = predicted if user_emotion and user_emotion != predicted and scores[predicted] > 0 else (user_emotion or predicted)
    return EmotionAnalysis(predicted_emotion=predicted, final_emotion=final, risk_level=RiskLevel.NONE, is_high_risk=False)
