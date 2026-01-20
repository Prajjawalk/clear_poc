"""Translation configuration for task monitoring models."""

from modeltranslation.translator import TranslationOptions, translator

from .models import TaskType


class TaskTypeTranslationOptions(TranslationOptions):
    """Translation options for TaskType model."""

    fields = ("name",)


translator.register(TaskType, TaskTypeTranslationOptions)
