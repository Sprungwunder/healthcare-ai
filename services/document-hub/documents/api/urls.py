from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import SimpleRouter

from documents.api import views

app_name = "api"

router = SimpleRouter()
router.register("documents", views.DocumentViewSet, basename="document")
router.register("tags", views.TagViewSet, basename="tag")

urlpatterns = [
    path("auth/token/", obtain_auth_token, name="token"),
    *router.urls,
]
