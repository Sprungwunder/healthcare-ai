from django.urls import path

from documents.web import views

app_name = "documents"

urlpatterns = [
    path("", views.DocumentListView.as_view(), name="list"),
    path("documents/new/", views.DocumentCreateView.as_view(), name="create"),
    path("documents/<uuid:pk>/", views.DocumentDetailView.as_view(), name="detail"),
    path(
        "documents/<uuid:pk>/edit/", views.DocumentUpdateView.as_view(), name="update"
    ),
    path(
        "documents/<uuid:pk>/delete/",
        views.DocumentDeleteView.as_view(),
        name="delete",
    ),
    path(
        "documents/<uuid:pk>/download/",
        views.DocumentDownloadView.as_view(),
        name="download",
    ),
]
