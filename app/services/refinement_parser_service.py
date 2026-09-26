"""
Purpose:
- Parse natural language refinements
- Extract height, environment, pose, lighting
- Validate clothing preservation intent
- Generate structured refinement context
- Support combined instructions
"""

import logging
import re
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class RefinementType(Enum):
    """Types of refinements"""
    HEIGHT = "height"
    ENVIRONMENT = "environment"
    POSE = "pose"
    LIGHTING = "lighting"
    CLOTHING_CHANGE = "clothing_change"
    ACCESSORY = "accessory"
    BACKGROUND = "background"
    MOOD = "mood"
    ACTION = "action"
    TIME_OF_DAY = "time_of_day"
    WEATHER = "weather"


@dataclass
class RefinementContext:
    """Structured refinement information"""
    original_instruction: str
    refinement_type: RefinementType
    value: str
    confidence: float  # 0-1
    preserves_clothing: bool = True
    priority: int = 1  # 1=high, 2=medium, 3=low


@dataclass
class ParsedRefinements:
    """All parsed refinements from instruction"""
    original_instruction: str
    refinements: List[RefinementContext]
    preserves_clothing: bool = True
    combined_prompt: str = ""
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class RefinementParserService:
    """Parse and process user refinement instructions"""

    def __init__(self):
        """Initialize refinement patterns and mappings"""
        self.height_patterns = self._init_height_patterns()
        self.environment_patterns = self._init_environment_patterns()
        self.pose_patterns = self._init_pose_patterns()
        self.lighting_patterns = self._init_lighting_patterns()
        self.clothing_patterns = self._init_clothing_patterns()
        self.mood_patterns = self._init_mood_patterns()
        logger.info("✅ Initialized RefinementParserService")

    def parse_refinement(self, instruction: str) -> ParsedRefinements:
        """
        Parse user refinement instruction
        
        Examples:
        - "My height is 5.8"
        - "I'm at a beach with sunset"
        - "Make me look casual at a party"
        - "5.8 height, beach, sunset lighting"
        """
        logger.info(f"📝 Parsing refinement: {instruction}")

        refinements = []
        preserves_clothing = True
        warnings = []

        # Check for clothing change intent
        if self._has_clothing_change_intent(instruction):
            preserves_clothing = False
            warnings.append("User may want to change clothing")
            logger.warning("⚠️ Instruction may involve clothing change")

        # Parse height
        height_match = self._parse_height(instruction)
        if height_match:
            refinements.append(height_match)
            logger.info(f"✅ Height detected: {height_match.value}")

        # Parse environment
        env_matches = self._parse_environment(instruction)
        refinements.extend(env_matches)
        if env_matches:
            logger.info(f"✅ Environments detected: {[e.value for e in env_matches]}")

        # Parse pose
        pose_match = self._parse_pose(instruction)
        if pose_match:
            refinements.append(pose_match)
            logger.info(f"✅ Pose detected: {pose_match.value}")

        # Parse lighting
        lighting_match = self._parse_lighting(instruction)
        if lighting_match:
            refinements.append(lighting_match)
            logger.info(f"✅ Lighting detected: {lighting_match.value}")

        # Parse mood
        mood_matches = self._parse_mood(instruction)
        refinements.extend(mood_matches)
        if mood_matches:
            logger.info(f"✅ Moods detected: {[m.value for m in mood_matches]}")

        # Sort by priority
        refinements.sort(key=lambda x: x.priority)

        # Build combined prompt
        combined_prompt = self._build_combined_prompt(refinements)

        result = ParsedRefinements(
            original_instruction=instruction,
            refinements=refinements,
            preserves_clothing=preserves_clothing,
            combined_prompt=combined_prompt,
            warnings=warnings,
        )

        logger.info(
            f"🎯 Parsed: {len(refinements)} refinements, "
            f"clothing_preserved={preserves_clothing}"
        )

        return result

    # ===== Height Parsing =====

    def _init_height_patterns(self) -> Dict[str, str]:
        """Height pattern matching"""
        return {
            "feet_inches": r"(\d+)['\"]?(\d+)['\"]?",  # 5'8" or 5 8
            "feet_only": r"(\d+\.?\d*)\s*(?:feet|ft)",
            "cm": r"(\d{2,3})\s*(?:cm|centimeter)",
            "inches": r"(\d+)\s*(?:inch|inches|in)",
        }

    def _parse_height(self, instruction: str) -> Optional[RefinementContext]:
        """Extract height from instruction"""
        lower = instruction.lower()

        # Look for height keywords
        if "height" not in lower and "tall" not in lower and "cm" not in lower:
            return None

        # Try feet/inches pattern (5'8" or 5 8)
        match = re.search(r"(\d+)['\"\s](\d+)", instruction)
        if match:
            feet = int(match.group(1))
            inches = int(match.group(2))
            return RefinementContext(
                original_instruction=instruction,
                refinement_type=RefinementType.HEIGHT,
                value=f"{feet}'{inches}\"",
                confidence=0.95,
                preserves_clothing=True,
                priority=1,
            )

        # Try feet only (175 cm → ~5.8)
        match = re.search(r"(\d{2,3})\s*cm", instruction, re.IGNORECASE)
        if match:
            cm = int(match.group(1))
            feet = cm // 30
            inches = int((cm % 30) / 2.54)
            return RefinementContext(
                original_instruction=instruction,
                refinement_type=RefinementType.HEIGHT,
                value=f"{cm}cm ({feet}'{inches}\")",
                confidence=0.9,
                preserves_clothing=True,
                priority=1,
            )

        return None

    # ===== Environment Parsing =====

    def _init_environment_patterns(self) -> Dict[str, List[str]]:
        """Environment keywords"""
        return {
            "beach": ["beach", "ocean", "sand", "seaside", "coastal"],
            "office": ["office", "work", "workplace", "conference"],
            "park": ["park", "outdoor", "nature", "garden"],
            "city": ["city", "urban", "street", "downtown"],
            "cafe": ["cafe", "coffee", "restaurant", "dining"],
            "party": ["party", "club", "nightclub", "dancing"],
            "mountain": ["mountain", "hiking", "trail", "forest"],
            "home": ["home", "house", "living room", "bedroom"],
            "gym": ["gym", "fitness", "workout"],
            "wedding": ["wedding", "ceremony", "celebration"],
        }

    def _parse_environment(self, instruction: str) -> List[RefinementContext]:
        """Extract environment from instruction"""
        results = []
        lower = instruction.lower()

        for env_type, keywords in self.environment_patterns.items():
            for keyword in keywords:
                if keyword in lower:
                    results.append(
                        RefinementContext(
                            original_instruction=instruction,
                            refinement_type=RefinementType.ENVIRONMENT,
                            value=env_type,
                            confidence=0.9,
                            preserves_clothing=True,
                            priority=1,
                        )
                    )
                    break  # Only one per environment type

        return results

    # ===== Pose Parsing =====

    def _init_pose_patterns(self) -> Dict[str, List[str]]:
        """Pose keywords"""
        return {
            "confident": ["confident", "confident", "standing tall", "proud"],
            "relaxed": ["relaxed", "casual", "comfortable", "at ease"],
            "sitting": ["sitting", "seated", "sit down"],
            "walking": ["walking", "walking", "strolling"],
            "jumping": ["jumping", "jumping", "jump"],
            "leaning": ["leaning", "lean"],
            "standing": ["standing", "stand"],
            "playful": ["playful", "playful", "fun", "silly"],
        }

    def _parse_pose(self, instruction: str) -> Optional[RefinementContext]:
        """Extract pose from instruction"""
        lower = instruction.lower()

        for pose_type, keywords in self.pose_patterns.items():
            for keyword in keywords:
                if keyword in lower:
                    return RefinementContext(
                        original_instruction=instruction,
                        refinement_type=RefinementType.POSE,
                        value=pose_type,
                        confidence=0.85,
                        preserves_clothing=True,
                        priority=2,
                    )

        return None

    # ===== Lighting Parsing =====

    def _init_lighting_patterns(self) -> Dict[str, List[str]]:
        """Lighting keywords"""
        return {
            "warm": ["warm", "golden", "sunset", "sunrise", "orange"],
            "cool": ["cool", "blue", "cold", "crisp"],
            "bright": ["bright", "sunny", "daylight", "sun"],
            "dim": ["dim", "dark", "moody", "shadows"],
            "golden_hour": ["golden hour", "golden", "sunset", "sunrise"],
            "sunset": ["sunset", "dusk", "evening"],
            "sunrise": ["sunrise", "dawn", "morning"],
            "overcast": ["overcast", "cloudy", "grey", "gray"],
            "dramatic": ["dramatic", "moody", "intense"],
        }

    def _parse_lighting(self, instruction: str) -> Optional[RefinementContext]:
        """Extract lighting from instruction"""
        lower = instruction.lower()

        for lighting_type, keywords in self.lighting_patterns.items():
            for keyword in keywords:
                if keyword in lower:
                    return RefinementContext(
                        original_instruction=instruction,
                        refinement_type=RefinementType.LIGHTING,
                        value=lighting_type,
                        confidence=0.85,
                        preserves_clothing=True,
                        priority=2,
                    )

        return None

    # ===== Clothing Change Detection =====

    def _init_clothing_patterns(self) -> Dict[str, List[str]]:
        """Clothing change keywords"""
        return {
            "change_top": ["change shirt", "different top", "wear a", "put on a"],
            "change_bottom": ["change pants", "different pants", "change bottoms"],
            "change_both": ["change outfit", "wear something", "different outfit"],
        }

    def _has_clothing_change_intent(self, instruction: str) -> bool:
        """Detect if user wants to change clothing"""
        lower = instruction.lower()

        for category, keywords in self.clothing_patterns.items():
            for keyword in keywords:
                if keyword in lower:
                    return True

        return False

    # ===== Mood Parsing =====

    def _init_mood_patterns(self) -> Dict[str, List[str]]:
        """Mood/vibe keywords"""
        return {
            "professional": ["professional", "formal", "business", "corporate"],
            "casual": ["casual", "relaxed", "laid-back", "chill"],
            "romantic": ["romantic", "romantic", "intimate", "soft"],
            "bold": ["bold", "daring", "stand out", "statement"],
            "minimal": ["minimal", "minimalist", "simple", "clean"],
            "edgy": ["edgy", "cool", "trendy", "modern"],
            "bohemian": ["bohemian", "boho", "hippie", "artistic"],
            "preppy": ["preppy", "classic", "traditional", "timeless"],
        }

    def _parse_mood(self, instruction: str) -> List[RefinementContext]:
        """Extract mood/vibe from instruction"""
        results = []
        lower = instruction.lower()

        for mood_type, keywords in self.mood_patterns.items():
            for keyword in keywords:
                if keyword in lower:
                    results.append(
                        RefinementContext(
                            original_instruction=instruction,
                            refinement_type=RefinementType.MOOD,
                            value=mood_type,
                            confidence=0.8,
                            preserves_clothing=True,
                            priority=3,
                        )
                    )
                    break

        return results

    # ===== Prompt Building =====

    def _build_combined_prompt(self, refinements: List[RefinementContext]) -> str:
        """Build combined refinement prompt"""
        if not refinements:
            return ""

        prompt_parts = []

        for ref in refinements:
            if ref.refinement_type == RefinementType.HEIGHT:
                prompt_parts.append(f"User height: {ref.value}. Adjust body proportions accordingly.")

            elif ref.refinement_type == RefinementType.ENVIRONMENT:
                prompt_parts.append(f"Environment: {ref.value}. Add appropriate background and setting.")

            elif ref.refinement_type == RefinementType.POSE:
                prompt_parts.append(f"Pose: {ref.value}. Model should be {ref.value}.")

            elif ref.refinement_type == RefinementType.LIGHTING:
                prompt_parts.append(f"Lighting: {ref.value} lighting. Adjust shadows and colors accordingly.")

            elif ref.refinement_type == RefinementType.MOOD:
                prompt_parts.append(f"Mood: {ref.value}. Overall aesthetic should feel {ref.value}.")

        combined = " ".join(prompt_parts)
        return combined

    def validate_clothing_preservation(
        self,
        original_instruction: str,
        parsed_refinements: ParsedRefinements,
    ) -> Dict[str, any]:
        """
        Validate that clothing will be preserved
        
        Returns:
        {
            "safe": True/False,
            "preserves_clothing": True/False,
            "warnings": [...],
            "recommendations": [...]
        }
        """
        safe = parsed_refinements.preserves_clothing
        warnings = list(parsed_refinements.warnings)
        recommendations = []

        # Check for dangerous patterns
        if any(
            word in original_instruction.lower()
            for word in ["change", "different", "wear", "put on"]
        ):
            if safe:
                warnings.append("Instruction contains clothing-related keywords but parsing determined clothing is preserved")
            recommendations.append("Verify that user doesn't intend to change clothing")

        return {
            "safe": safe,
            "preserves_clothing": parsed_refinements.preserves_clothing,
            "warnings": warnings,
            "recommendations": recommendations,
        }

    def get_refinement_summary(self, parsed: ParsedRefinements) -> str:
        """Get human-readable summary of refinements"""
        if not parsed.refinements:
            return "No refinements detected"

        summary_parts = []
        for ref in parsed.refinements:
            summary_parts.append(f"{ref.refinement_type.value}: {ref.value}")

        return " | ".join(summary_parts)