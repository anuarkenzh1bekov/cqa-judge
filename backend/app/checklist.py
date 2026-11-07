"""Checklist schema + the default checklist from CQA_Chat_Quality_Checklist.pdf.

Criterion types:
  binary - answers "yes" / "no" (+ "na" if na_allowed). yes = full weight, no = 0.
  scale  - answer is one of scale[].value (+ "na"). points = value / max(scale) * weight.
  flag   - no points (weight must be 0); "yes" marks a gross error reported separately.
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def fmt_num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


class ScaleLevel(BaseModel):
    value: float
    description: str


class Criterion(BaseModel):
    key: str = Field(pattern=r"^[A-Za-z0-9_\-]{1,40}$")
    section: str | None = None
    name: str
    description: str  # what "yes" / the scale means
    type: Literal["binary", "scale", "flag"]
    weight: float = Field(ge=0)
    na_allowed: bool = False
    na_condition: str | None = None
    scale: list[ScaleLevel] | None = None
    guidance: str | None = None  # extra hints for the evaluator (edge cases, examples)

    @field_validator("scale")
    @classmethod
    def _sort_scale(cls, v):
        if v is not None:
            v = sorted(v, key=lambda s: s.value, reverse=True)
            if len({s.value for s in v}) != len(v):
                raise ValueError("scale values must be unique")
        return v

    @model_validator(mode="after")
    def _check(self):
        if self.type == "scale" and (not self.scale or len(self.scale) < 2):
            raise ValueError(f"{self.key}: scale criterion needs at least 2 levels")
        if self.type == "scale" and max(s.value for s in self.scale) <= 0:
            raise ValueError(f"{self.key}: top scale level must be > 0")
        if self.type != "scale" and self.scale:
            raise ValueError(f"{self.key}: only scale criteria have a scale")
        if self.type == "flag" and self.weight != 0:
            raise ValueError(f"{self.key}: flag criteria carry no points (weight must be 0)")
        if self.na_allowed and not self.na_condition:
            raise ValueError(f"{self.key}: na_condition is required when N/A is allowed")
        return self

    def allowed_answers(self) -> list[str]:
        if self.type == "scale":
            base = [fmt_num(s.value) for s in self.scale]
        else:
            base = ["yes", "no"]
        return base + (["na"] if self.na_allowed else [])


class ChecklistIn(BaseModel):
    name: str
    description: str | None = None
    criteria: list[Criterion] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_keys(self):
        keys = [c.key for c in self.criteria]
        if len(keys) != len(set(keys)):
            raise ValueError("criterion keys must be unique")
        return self


DEFAULT_CHECKLIST = {
    "name": "Чек-лист качества чатов (Freedom Broker)",
    "description": "Стартовая конфигурация из CQA_Chat_Quality_Checklist.pdf",
    "criteria": [
        {
            "key": "c01_contact", "section": "Начало и понимание запроса", "name": "Установление контакта",
            "type": "binary", "weight": 10, "na_allowed": False,
            "description": "Да — оператор поздоровался на языке клиента и представился в первом ответе.",
            "guidance": "Оценивается ПЕРВАЯ реплика оператора (не бота). Нужны оба элемента: приветствие на языке клиента "
                        "и представление (имя). Приветствие бота не засчитывается. В звонке имя может быть скрыто "
                        "маской «[Имя скрыто]» — это считается представлением.",
        },
        {
            "key": "c02_needs", "section": "Начало и понимание запроса", "name": "Выявление потребности",
            "type": "binary", "weight": 15, "na_allowed": True,
            "description": "Да — оператор учёл известные детали и уточнил недостающее до ответа.",
            "na_condition": "Данных для ответа хватало с самого начала.",
            "guidance": "Известные детали — в том числе то, что клиент уже написал боту. «Нет», если оператор переспросил "
                        "уже известное или ответил, не уточнив недостающее (и ответ из-за этого неточен).",
        },
        {
            "key": "c03_identification", "section": "Безопасность и решение", "name": "Идентификация",
            "type": "binary", "weight": 20, "na_allowed": True,
            "description": "Да — проверка личности подтверждена до раскрытия данных или защищённого действия.",
            "na_condition": "Запрос не требовал идентификации.",
            "guidance": "Общий вопрос о тарифах, продуктах, интерфейсе приложения не требует идентификации → N/A. "
                        "Если требовалась проверка личности перед раскрытием данных клиента (баланс, сделки, персональные "
                        "данные счёта) или защищённым действием, и она не подтверждена в чате ДО этого → «Нет». "
                        "Системное сообщение «Личность клиента подтверждена» / «Customer identity verified» / "
                        "«Клиенттің жеке басы расталды» считается подтверждением.",
        },
        {
            "key": "c04_consultation", "section": "Безопасность и решение", "name": "Корректная и полная консультация",
            "type": "scale", "weight": 20, "na_allowed": True,
            "description": "Оцените ответ или следующий шаг по шкале.",
            "na_condition": "Чат закончился до того, как клиент сформулировал запрос.",
            "scale": [
                {"value": 20, "description": "Все существенные вопросы закрыты или дан корректный следующий шаг."},
                {"value": 15, "description": "Основной вопрос решён, пропущена второстепенная деталь."},
                {"value": 10, "description": "Часть запроса закрыта, существенный вопрос остался открытым."},
                {"value": 5, "description": "Есть общая подсказка, но клиенту всё ещё непонятно, как действовать."},
                {"value": 0, "description": "Ответа по существу нет или ключевая рекомендация ошибочна."},
            ],
            "guidance": "Консультация оценивает, правильно и полно ли решён запрос (а не стиль общения). Ясный ответ на один "
                        "из двух важных вопросов — частичный балл.",
        },
        {
            "key": "c05_empathy", "section": "Ведение и завершение диалога", "name": "Эмпатия и клиентоориентированность",
            "type": "binary", "weight": 15, "na_allowed": False,
            "description": "Да — оператор вежлив и, если клиент выразил недовольство или описал неудобство, "
                           "отреагировал на конкретную проблему.",
            "guidance": "Если клиент не выражал недовольства и не описывал неудобства — достаточно вежливости. "
                        "Шаблонное «извините за неудобства» без реакции на конкретную проблему — «Нет».",
        },
        {
            "key": "c06_management", "section": "Ведение и завершение диалога",
            "name": "Управление диалогом, скорость и грамотность",
            "type": "scale", "weight": 15, "na_allowed": False,
            "description": "Оцените ясность, порядок ответов и предупреждение об ожидании по шкале.",
            "scale": [
                {"value": 10, "description": "Ответы ясные и связные. Если было явное ожидание, оператор предупредил."},
                {"value": 7, "description": "Один заметный сбой, но клиент может понять ответ и продолжить."},
                {"value": 4, "description": "Клиенту приходится переспрашивать из-за формулировок или порядка ответов."},
                {"value": 0, "description": "Из-за бессвязных или противоречивых реплик ход диалога непонятен."},
            ],
            "guidance": "Порог первой реакции (3 минуты), теги и вложения в оценку не входят. В звонках ошибки "
                        "автоматической транскрибации не считаются ошибками оператора.",
        },
        {
            "key": "c07_closing", "section": "Ведение и завершение диалога", "name": "Завершение",
            "type": "binary", "weight": 5, "na_allowed": True,
            "description": "Да — оператор подвёл итог или предложил дальнейшую помощь и попрощался.",
            "na_condition": "Чат оборвался до возможности его завершить.",
            "guidance": "Нужны оба элемента: (итог ИЛИ предложение дальнейшей помощи) И прощание. "
                        "Итог — в заключительной реплике оператор кратко фиксирует результат или следующий шаг "
                        "(«начните со сверки дат», «вопрос передан, ответим здесь», «перед переводом проверьте комиссию»). "
                        "Предложение помощи — «если вопрос останется, напишите», «чем ещё помочь?». "
                        "Одно лишь «Пожалуйста. Хорошего дня!» / «You're welcome. Bye!» без итога и без предложения "
                        "помощи — «Нет». Если оператор закрыл чат без прощания — «Нет». Если клиент сам ушёл или связь "
                        "прервалась, и у оператора не было возможности завершить — N/A. Применяй правило одинаково "
                        "для всех языков.",
        },
        {
            "key": "c08_gross", "section": "Грубые нарушения", "name": "Грубые ошибки",
            "type": "flag", "weight": 0, "na_allowed": False,
            "description": "Да — выявлено оскорбление клиента, предложение платной услуги в обход компании или раскрытие "
                           "конфиденциальной информации. Нет — ни одно из трёх не выявлено.",
            "guidance": "Услуга в обход компании: оператор предлагает перевести деньги ему лично для инвестирования или "
                        "просит личный номер клиента, чтобы оказать платную консультацию в частном порядке. Достаточно "
                        "самого предложения; согласие клиента или перевод не требуются. Раскрытие конфиденциальной "
                        "информации — например, данных другого клиента или внутренних данных компании.",
        },
    ],
}
