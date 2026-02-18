from django.urls import path

from .views import (
    AnalysisRunDetailView,
    AnalysisRunListView,
    AnalysisRunStatusView,
    ExportPDFView,
    StartAnalysisView,
)

app_name = "analyzer"

urlpatterns = [
    path("analyze/", StartAnalysisView.as_view(), name="start-analysis"),
    path("runs/", AnalysisRunListView.as_view(), name="run-list"),
    path("runs/<int:run_id>/", AnalysisRunDetailView.as_view(), name="run-detail"),
    path("runs/<int:run_id>/status/", AnalysisRunStatusView.as_view(), name="run-status"),
    path("runs/<int:run_id>/export-pdf/", ExportPDFView.as_view(), name="export-pdf"),
]
