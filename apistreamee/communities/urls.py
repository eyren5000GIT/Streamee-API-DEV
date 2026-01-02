from django.urls import path
from . import views

urlpatterns = [
    # Communities
    path("communities/", views.community_list_create, name="community-list-create"),
    path("communities/slug/<slug:slug>/", views.community_detail_by_slug, name="community-detail-by-slug"),
    path("communities/<int:pk>/", views.community_patch_by_id, name="community-patch-by-id"),

    # Membership actions
    path("communities/<int:pk>/join/", views.community_join, name="community-join"),
    path("communities/<int:pk>/leave/", views.community_leave, name="community-leave"),

    # Me
    path("me/communities/", views.me_communities, name="me-communities"),
]
