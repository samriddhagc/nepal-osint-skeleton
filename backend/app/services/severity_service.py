"""Severity grading service for news stories."""
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class SeverityLevel(str, Enum):
    """Severity classification levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class SeverityResult:
    """Result of severity classification."""
    level: SeverityLevel
    triggers: list[str]


class SeverityService:
    """
    Rules-based severity grading service.

    Severity levels:
    - critical: death, killed, bomb, explosion, earthquake magnitude >5, emergency declared
    - high: injured, arrest, flood, landslide, clash, violence, strike affecting >1000
    - medium: nepal_relevance=DOMESTIC + relevance_score > 0.7
    - low: Everything else
    """

    # Critical keywords - immediate threat to life or major disaster
    # English keywords
    CRITICAL_KEYWORDS_EN = [
        "killed", "death", "dead", "dies", "died", "fatality", "fatalities",
        "bomb", "bombing", "explosion", "blast", "detonate",
        "earthquake", "magnitude", "tremor", "quake",
        "emergency declared", "state of emergency", "curfew",
        "massacre", "mass casualty", "multiple deaths",
        "terror", "terrorist",
        "plane crash", "air crash", "helicopter crash",
        "collapse", "building collapse",
    ]

    # Nepali critical keywords (मृत्यु = death, हत्या = murder, etc.)
    CRITICAL_KEYWORDS_NE = [
        "मृत्यु", "मारिए", "मारिएको", "ज्यान गुमाए", "ज्यान गयो",
        "हत्या", "बम", "विस्फोट", "भूकम्प", "भुकम्प",
        "आपतकालीन", "कर्फ्यु", "आतंक", "आतंकवादी",
        "दुर्घटना", "हेलिकप्टर दुर्घटना", "विमान दुर्घटना",
        "भत्किएको", "ढलेको",
    ]

    # High severity keywords - significant harm or disruption
    HIGH_KEYWORDS_EN = [
        "injured", "injury", "injuries", "wounded", "hospitalized",
        "arrest", "arrested", "custody", "detained",
        "flood", "flooding", "inundation", "submerged",
        "landslide", "mudslide", "debris flow",
        "avalanche", "snowslide",
        "clash", "clashes", "violence", "violent",
        "strike", "bandh", "shutdown", "blockade",
        "protest", "demonstration", "rally", "agitation",
        "fire", "blaze", "inferno", "gutted",
        "accident", "collision", "crash",
        "kidnap", "abduct", "hostage",
        "robbery", "theft", "burglary", "looted",
        "murder", "homicide", "stabbing", "shooting",
        "assault", "beat", "beaten",
        "rape", "sexual assault",
        "riot", "rioting",
        "border tension", "border dispute",
    ]

    # Nepali high severity keywords
    HIGH_KEYWORDS_NE = [
        "घाइते", "घाइतेको", "अस्पताल भर्ना", "उपचाररत",
        "पक्राउ", "गिरफ्तार", "हिरासत",
        "बाढी", "डुबान", "पहिरो", "हिउँ पहिरो",
        "हिमपहिरो", "झडप", "हिंसा", "हिंसात्मक",
        "हडताल", "बन्द", "चक्काजाम", "आन्दोलन",
        "आगलागी", "आगो लागेको", "जलेर",
        "दुर्घटना", "ठोक्किएको",
        "अपहरण", "लुटपाट", "चोरी",
        "हत्या", "गोली चलाएको", "छुरा प्रहार",
        "आक्रमण", "कुटपिट", "बलात्कार",
        "दंगा", "सीमा तनाव",
    ]

    # Medium severity keywords - notable but not immediately threatening
    MEDIUM_KEYWORDS_EN = [
        "warning", "alert", "advisory",
        "investigation", "probe", "inquiry",
        "dispute", "conflict", "tension",
        "shortage", "crisis", "scarcity",
        "corruption", "scandal", "fraud",
        "price hike", "inflation",
        "unemployment", "layoff",
        "pollution", "contamination",
        "disease outbreak", "epidemic",
        "political crisis", "government crisis",
    ]

    # Nepali medium severity keywords
    MEDIUM_KEYWORDS_NE = [
        "चेतावनी", "सतर्कता", "सूचना",
        "अनुसन्धान", "छानबिन",
        "विवाद", "तनाव", "द्वन्द्व",
        "अभाव", "संकट",
        "भ्रष्टाचार", "घोटाला", "ठगी",
        "महंगी", "मुद्रास्फीति",
        "बेरोजगारी",
        "प्रदूषण",
        "रोग फैलावट", "महामारी",
        "राजनीतिक संकट",
    ]

    # Keywords that should NOT trigger severity (sports, entertainment, etc.)
    EXCLUSION_CONTEXTS = [
        # Cricket/Sports contexts that have "dies" in words
        r"\bwindies\b", r"\bwest indies\b", r"\bt20\b", r"\bipl\b",
        r"\bworld cup\b", r"\bsquad\b", r"\bteam\b", r"\bmatch\b",
        r"\btournament\b", r"\bchampionship\b", r"\bseries\b",
        r"\bplayer\b", r"\bcricketer\b", r"\bcaptain\b",
        # Entertainment
        r"\bfilm\b", r"\bmovie\b", r"\bactor\b", r"\bactress\b",
        r"\bbollywood\b", r"\bhollywood\b", r"\box office\b",
    ]

    def __init__(self):
        """Initialize severity service with compiled regex patterns."""
        # Compile word boundary patterns for English keywords
        self._critical_patterns = [
            re.compile(r'\b' + re.escape(k.lower()) + r'\b', re.IGNORECASE)
            for k in self.CRITICAL_KEYWORDS_EN
        ]
        self._high_patterns = [
            re.compile(r'\b' + re.escape(k.lower()) + r'\b', re.IGNORECASE)
            for k in self.HIGH_KEYWORDS_EN
        ]
        self._medium_patterns = [
            re.compile(r'\b' + re.escape(k.lower()) + r'\b', re.IGNORECASE)
            for k in self.MEDIUM_KEYWORDS_EN
        ]

        # Nepali keywords (no word boundaries needed for Devanagari)
        self._critical_ne = [k.lower() for k in self.CRITICAL_KEYWORDS_NE]
        self._high_ne = [k.lower() for k in self.HIGH_KEYWORDS_NE]
        self._medium_ne = [k.lower() for k in self.MEDIUM_KEYWORDS_NE]

        # Exclusion patterns
        self._exclusion_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in self.EXCLUSION_CONTEXTS
        ]

    def _is_excluded_context(self, text: str) -> bool:
        """Check if text is in an excluded context (sports, entertainment, etc.)."""
        exclusion_count = 0
        for pattern in self._exclusion_patterns:
            if pattern.search(text):
                exclusion_count += 1
                if exclusion_count >= 2:  # Multiple sports/entertainment indicators
                    return True
        return False

    def grade(
        self,
        title: str,
        content: Optional[str],
        nepal_relevance: Optional[str] = None,
        relevance_score: Optional[float] = None,
    ) -> SeverityResult:
        """
        Grade story severity based on content.

        Args:
            title: Story title
            content: Story content/summary (optional)
            nepal_relevance: Nepal relevance level (optional)
            relevance_score: Relevance score 0-1 (optional)

        Returns:
            SeverityResult with level and trigger keywords
        """
        text = f"{title} {content or ''}".lower()
        triggers: list[str] = []

        # Check if this is sports/entertainment context - downgrade severity
        is_excluded = self._is_excluded_context(text)

        # Check critical keywords (English with word boundaries)
        for pattern in self._critical_patterns:
            if pattern.search(text):
                keyword = pattern.pattern.replace(r'\b', '').replace('\\', '')
                triggers.append(keyword)
                if len(triggers) >= 3:
                    break

        # Check critical keywords (Nepali)
        for keyword in self._critical_ne:
            if keyword in text:
                triggers.append(keyword)
                if len(triggers) >= 3:
                    break

        if triggers and not is_excluded:
            return SeverityResult(
                level=SeverityLevel.CRITICAL,
                triggers=triggers[:5],
            )
        elif triggers and is_excluded:
            # Downgrade to medium for sports/entertainment with "critical" words
            return SeverityResult(
                level=SeverityLevel.MEDIUM,
                triggers=triggers[:3] + ["[sports/entertainment context]"],
            )

        # Check high keywords (English with word boundaries)
        triggers = []
        for pattern in self._high_patterns:
            if pattern.search(text):
                keyword = pattern.pattern.replace(r'\b', '').replace('\\', '')
                triggers.append(keyword)
                if len(triggers) >= 3:
                    break

        # Check high keywords (Nepali)
        for keyword in self._high_ne:
            if keyword in text:
                triggers.append(keyword)
                if len(triggers) >= 3:
                    break

        if triggers and not is_excluded:
            return SeverityResult(
                level=SeverityLevel.HIGH,
                triggers=triggers[:5],
            )
        elif triggers and is_excluded:
            # Downgrade to low for sports/entertainment
            return SeverityResult(
                level=SeverityLevel.LOW,
                triggers=triggers[:3] + ["[sports/entertainment context]"],
            )

        # Check medium keywords (English with word boundaries)
        triggers = []
        for pattern in self._medium_patterns:
            if pattern.search(text):
                keyword = pattern.pattern.replace(r'\b', '').replace('\\', '')
                triggers.append(keyword)
                if len(triggers) >= 2:
                    break

        # Check medium keywords (Nepali)
        for keyword in self._medium_ne:
            if keyword in text:
                triggers.append(keyword)
                if len(triggers) >= 2:
                    break

        if triggers:
            return SeverityResult(
                level=SeverityLevel.MEDIUM,
                triggers=triggers[:5],
            )

        # Relevance-based medium
        if nepal_relevance == "NEPAL_DOMESTIC" and relevance_score and relevance_score > 0.7:
            return SeverityResult(
                level=SeverityLevel.MEDIUM,
                triggers=["high_relevance_domestic"],
            )

        # Default to low
        return SeverityResult(
            level=SeverityLevel.LOW,
            triggers=[],
        )

    def get_severity_value(self, level: SeverityLevel) -> int:
        """Get numeric severity value for comparisons."""
        values = {
            SeverityLevel.CRITICAL: 4,
            SeverityLevel.HIGH: 3,
            SeverityLevel.MEDIUM: 2,
            SeverityLevel.LOW: 1,
        }
        return values.get(level, 0)

    def get_highest_severity(self, levels: list[SeverityLevel]) -> SeverityLevel:
        """Get the highest severity from a list."""
        if not levels:
            return SeverityLevel.LOW

        return max(levels, key=lambda x: self.get_severity_value(x))
