# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Module imports
from .base import BaseSerializer
from .user import UserLiteSerializer
from .project import ProjectLiteSerializer
from .workspace import WorkspaceLiteSerializer
from plane.db.models import Importer, IssueImport


class ImporterSerializer(BaseSerializer):
    initiated_by_detail = UserLiteSerializer(source="initiated_by", read_only=True)
    project_detail = ProjectLiteSerializer(source="project", read_only=True)
    workspace_detail = WorkspaceLiteSerializer(source="workspace", read_only=True)

    class Meta:
        model = Importer
        fields = "__all__"


class IssueImportSerializer(BaseSerializer):
    initiated_by_detail = UserLiteSerializer(source="initiated_by", read_only=True)

    class Meta:
        model = IssueImport
        fields = "__all__"
        read_only_fields = [
            "id",
            "workspace",
            "project",
            "status",
            "total_rows",
            "created_rows",
            "skipped_rows",
            "failed_rows",
            "error_report",
            "created_at",
            "updated_at",
        ]
