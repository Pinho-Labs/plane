# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.conf import settings
from django.db import models

# Module imports
from .project import ProjectBaseModel


class Importer(ProjectBaseModel):
    service = models.CharField(max_length=50, choices=(("github", "GitHub"), ("jira", "Jira")))
    status = models.CharField(
        max_length=50,
        choices=(
            ("queued", "Queued"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ),
        default="queued",
    )
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="imports")
    metadata = models.JSONField(default=dict)
    config = models.JSONField(default=dict)
    data = models.JSONField(default=dict)
    token = models.ForeignKey("db.APIToken", on_delete=models.CASCADE, related_name="importer")
    imported_data = models.JSONField(null=True)

    class Meta:
        verbose_name = "Importer"
        verbose_name_plural = "Importers"
        db_table = "importers"
        ordering = ("-created_at",)

    def __str__(self):
        """Return name of the service"""
        return f"{self.service} <{self.project.name}>"


class IssueImport(ProjectBaseModel):
    """Tracks a CSV bulk work-item import run for status + history.

    Purpose-built (not reusing the OAuth-oriented `Importer` above): no required
    API-token FK, `SET_NULL` on the initiator so audit history survives user
    deletion, and typed/indexable counters instead of a JSON blob.
    """

    STATUS_CHOICES = (
        ("queued", "Queued"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    )
    file_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued")
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="issue_imports",
    )
    total_rows = models.PositiveIntegerField(default=0)
    created_rows = models.PositiveIntegerField(default=0)
    skipped_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    error_report = models.JSONField(default=list)  # [{"row": int, "field": str, "message": str}]
    external_source = models.CharField(max_length=50, default="csv")

    class Meta:
        verbose_name = "Issue Import"
        verbose_name_plural = "Issue Imports"
        db_table = "issue_imports"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.file_name} <{self.status}>"
