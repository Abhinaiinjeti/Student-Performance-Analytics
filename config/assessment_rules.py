"""
EduPulse Analytics - Assessment Rules & Evaluation Criteria Engine
Supports semester results, mid exams, internal assessments, laboratories, practicals,
assignments, quizzes, projects, vivas, and custom assessment components.
"""
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Any, List


@dataclass
class AssessmentTypeConfig:
    """Configurable metadata and thresholds for an academic assessment category."""
    type_id: str
    display_name: str
    category: str  # 'mid', 'semester', 'internal', 'lab', 'assignment', 'quiz', 'project', 'viva', 'custom'
    default_max_marks: float = 100.0
    default_pass_marks: float = 40.0
    weightage: float = 1.0
    is_grade_based: bool = False
    description: str = ""

    def evaluate(self, marks_obtained: Optional[float], explicit_status: Optional[str] = None) -> Tuple[str, Optional[float]]:
        """Evaluates obtained marks against assessment max and pass marks."""
        if explicit_status:
            norm = explicit_status.strip().upper()
            if norm in ("ABSENT", "AB"):
                return "ABSENT", None
            if norm in ("WITHHELD", "W", "WH"):
                return "WITHHELD", None
            if norm in ("INCOMPLETE", "I"):
                return "INCOMPLETE", None

        if marks_obtained is None:
            return "INCOMPLETE", None

        if marks_obtained < 0 or marks_obtained > self.default_max_marks:
            return "INVALID", None

        is_passed = marks_obtained >= self.default_pass_marks
        return ("PASS" if is_passed else "FAIL"), marks_obtained


# Standard academic assessment types
STANDARD_ASSESSMENT_TYPES: Dict[str, AssessmentTypeConfig] = {
    "semester_exam": AssessmentTypeConfig(
        type_id="semester_exam",
        display_name="Semester Examination",
        category="semester",
        default_max_marks=100.0,
        default_pass_marks=40.0,
        weightage=1.0,
        description="End-semester comprehensive university or institutional examination"
    ),
    "mid_1": AssessmentTypeConfig(
        type_id="mid_1",
        display_name="Mid-1 Examination",
        category="mid",
        default_max_marks=40.0,
        default_pass_marks=16.0,
        weightage=0.5,
        description="First mid-term internal written examination"
    ),
    "mid_2": AssessmentTypeConfig(
        type_id="mid_2",
        display_name="Mid-2 Examination",
        category="mid",
        default_max_marks=40.0,
        default_pass_marks=16.0,
        weightage=0.5,
        description="Second mid-term internal written examination"
    ),
    "internal": AssessmentTypeConfig(
        type_id="internal",
        display_name="Internal Assessment / Sessional",
        category="internal",
        default_max_marks=40.0,
        default_pass_marks=16.0,
        weightage=0.4,
        description="Continuous internal evaluation (CIA) consolidated marks"
    ),
    "laboratory": AssessmentTypeConfig(
        type_id="laboratory",
        display_name="Laboratory / Practical Assessment",
        category="lab",
        default_max_marks=50.0,
        default_pass_marks=20.0,
        weightage=1.0,
        description="Practical experiment, continuous lab record, and viva"
    ),
    "practical": AssessmentTypeConfig(
        type_id="practical",
        display_name="Practical Examination",
        category="lab",
        default_max_marks=50.0,
        default_pass_marks=20.0,
        weightage=1.0,
        description="End-semester external practical examination"
    ),
    "assignment": AssessmentTypeConfig(
        type_id="assignment",
        display_name="Assignment / Coursework",
        category="assignment",
        default_max_marks=10.0,
        default_pass_marks=4.0,
        weightage=0.1,
        description="Student assignment submissions, tutorials, or homework"
    ),
    "quiz": AssessmentTypeConfig(
        type_id="quiz",
        display_name="Quiz / Class Test",
        category="quiz",
        default_max_marks=10.0,
        default_pass_marks=4.0,
        weightage=0.1,
        description="Objective tests, quizzes, or short weekly assessments"
    ),
    "project": AssessmentTypeConfig(
        type_id="project",
        display_name="Project / Presentation",
        category="project",
        default_max_marks=100.0,
        default_pass_marks=50.0,
        weightage=1.0,
        description="Capstone, mini-project, seminar, or technical presentation"
    ),
    "viva": AssessmentTypeConfig(
        type_id="viva",
        display_name="Viva Voce",
        category="viva",
        default_max_marks=50.0,
        default_pass_marks=25.0,
        weightage=0.5,
        description="Oral examination and comprehensive viva assessment"
    ),
    "custom": AssessmentTypeConfig(
        type_id="custom",
        display_name="Custom Assessment",
        category="custom",
        default_max_marks=100.0,
        default_pass_marks=40.0,
        weightage=1.0,
        description="User-defined custom assessment component"
    )
}


@dataclass
class SubjectMarksRule:
    """Configurable marks limits and passing thresholds for a subject."""
    subject_code: str
    subject_name: str
    max_internal: float = 40.0
    max_external: float = 60.0
    min_internal_pass: float = 16.0  # 40% of max internal
    min_external_pass: float = 24.0  # 40% of max external
    min_total_pass: float = 40.0     # 40% of max total

    @property
    def max_total(self) -> float:
        return self.max_internal + self.max_external

    def evaluate_result(
        self,
        internal: Optional[float],
        external: Optional[float],
        explicit_status: Optional[str] = None
    ) -> Tuple[str, Optional[float]]:
        """
        Evaluates student marks against configured thresholds.
        Returns: (status: str, total_marks: Optional[float])
        """
        # Handle explicit administrative statuses
        if explicit_status:
            normalized_status = explicit_status.strip().upper()
            if normalized_status in ("ABSENT", "AB"):
                return "ABSENT", None
            if normalized_status in ("WITHHELD", "W", "WH"):
                return "WITHHELD", None
            if normalized_status in ("INCOMPLETE", "I"):
                return "INCOMPLETE", None

        # Check for missing components
        if internal is None or external is None:
            return "INCOMPLETE", None

        # Check bounds
        if internal < 0 or internal > self.max_internal or external < 0 or external > self.max_external:
            return "INVALID", None

        total = round(internal + external, 2)

        # Check passing criteria
        is_passed = (
            internal >= self.min_internal_pass and
            external >= self.min_external_pass and
            total >= self.min_total_pass
        )

        return ("PASS" if is_passed else "FAIL"), total


@dataclass
class GradeScaleRule:
    """Configurable university letter grade to grade point mapping."""
    grade_points: Dict[str, float] = field(default_factory=lambda: {
        "O": 10.0,
        "A+": 9.0,
        "A": 8.0,
        "B+": 7.0,
        "B": 6.0,
        "C": 5.0,
        "P": 4.0,
        "F": 0.0
    })
    pass_grades: Tuple[str, ...] = ("O", "A+", "A", "B+", "B", "C", "P")
    fail_grades: Tuple[str, ...] = ("F", "U", "FAIL")
    absent_markers: Tuple[str, ...] = ("AB", "ABS", "ABSENT")
    withheld_markers: Tuple[str, ...] = ("W", "WH", "WITHHELD")

    def classify_grade(self, raw_grade: Optional[str]) -> Tuple[str, Optional[float]]:
        """
        Classifies raw letter grade string.
        Returns: (canonical_status: str, grade_point: Optional[float])
        """
        if raw_grade is None or str(raw_grade).strip() in ("", "-", "NULL", "NONE", "NAN"):
            return "MISSING", None

        grade = str(raw_grade).strip().upper()

        if grade in self.absent_markers:
            return "ABSENT", None
        if grade in self.withheld_markers:
            return "WITHHELD", None
        if grade in self.pass_grades:
            return "PASSED", self.grade_points.get(grade)
        if grade in self.fail_grades:
            return "FAILED", self.grade_points.get(grade, 0.0)

        return "UNKNOWN", None


class AssessmentRules:
    """Master registry for institutional assessment rules."""
    def __init__(self):
        self.default_marks_rule = SubjectMarksRule(
            subject_code="DEFAULT",
            subject_name="Default Subject Assessment",
            max_internal=40.0,
            max_external=60.0,
            min_internal_pass=16.0,
            min_external_pass=24.0,
            min_total_pass=40.0
        )
        self.grade_rule = GradeScaleRule()
        self.subject_rules: Dict[str, SubjectMarksRule] = {}
        self.assessment_types: Dict[str, AssessmentTypeConfig] = dict(STANDARD_ASSESSMENT_TYPES)

    def get_marks_rule(self, subject_code: str) -> SubjectMarksRule:
        return self.subject_rules.get(subject_code.strip().upper(), self.default_marks_rule)

    def register_subject_rule(self, rule: SubjectMarksRule) -> None:
        self.subject_rules[rule.subject_code.strip().upper()] = rule

    def get_assessment_type(self, type_id: str) -> AssessmentTypeConfig:
        return self.assessment_types.get(type_id, self.assessment_types["custom"])

    def register_assessment_type(self, config: AssessmentTypeConfig) -> None:
        self.assessment_types[config.type_id] = config

    def list_assessment_types(self) -> List[Dict[str, Any]]:
        return [
            {
                "type_id": t.type_id,
                "display_name": t.display_name,
                "category": t.category,
                "default_max_marks": t.default_max_marks,
                "default_pass_marks": t.default_pass_marks,
                "weightage": t.weightage,
                "description": t.description
            }
            for t in self.assessment_types.values()
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "default_marks_rule": {
                "max_internal": self.default_marks_rule.max_internal,
                "max_external": self.default_marks_rule.max_external,
                "min_internal_pass": self.default_marks_rule.min_internal_pass,
                "min_external_pass": self.default_marks_rule.min_external_pass,
                "min_total_pass": self.default_marks_rule.min_total_pass,
            },
            "grade_points": self.grade_rule.grade_points,
            "pass_grades": list(self.grade_rule.pass_grades),
            "fail_grades": list(self.grade_rule.fail_grades),
            "assessment_types": self.list_assessment_types()
        }
