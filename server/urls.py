"""
URL configuration for server project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.urls import re_path
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),

    #AUTH
    path('auth/login/', views.auth_login),
    path('auth/signup/', views.auth_signup),
    path('auth/validate_token/', views.auth_validate_token),

    #USER
    path('user/get_company_users/', views.get_users_by_company), #for search to add to team
    path('user/get_company_users_but_not_team/', views.get_users_by_company_but_not_team), #for search to add to team
    path('user/get_user_components_favorites/', views.get_user_components_favorites),
    path('user/toggle_favorite/<int:component_id>/', views.toggle_favorite),

    #COMPONENT
    path('component/create_component/', views.create_component),
    path('component/get_component_by_id/<int:pk>/', views.get_component_by_ID),
    path('component/get_user_components_all/', views.get_user_components_all),
    path('component/get_user_components_my_components/', views.get_user_components_my_components),
    path('component/get_components_default/', views.get_components_default),
    path('component/get_components_public/', views.get_components_public),
    path('component/get_component_teams/<int:component_id>/', views.get_component_teams), #dont know why this needs to end with a "/"
    path('component/delete/<int:component_id>', views.delete_component),

    #TEAMS
    path('teams/get_user_teams_all/', views.get_user_teams_all),
    path('teams/get_user_teams_all_details/', views.get_user_teams_all_details),
    path('teams/create_new_team/', views.create_team),
    
    path('teams/get_users_in_team/<int:team_id>/', views.get_users_in_team, name='get_users_in_team'),
    path('teams/add_user_to_team/<int:team_id>/', views.add_user_to_team, name='add_user_to_team'),
    path('teams/remove_user_from_team/<int:team_id>/', views.remove_user_from_team, name='remove_user_from_team'),

    path('teams/add_components/team/<int:team_id>/component/<int:component_id>/', views.add_component_to_team, name='add_component_to_team'),
    path('teams/remove_components/team/<int:team_id>/component/<int:component_id>/', views.remove_component_from_team, name='remove_component_from_team'),
    path('teams/get_team_components/<int:team_id>/', views.get_team_components),
   
    path('teams/get_team_role/<int:team_id>/', views.get_team_role),
    path('teams/get_all_roles/', views.get_all_roles),
    path('teams/change_user_role/team/<int:team_id>/user/<int:user_id>/', views.change_user_role),

    #COMPANY
    #Create New Company
    path('company/create/', views.create_company),
    path('company/verify/<uuid:token>/', views.verify_company_token),

    # Company Roles
    path('company/roles/', views.get_all_company_roles),
    path('company/roles/<int:role_id>/', views.get_company_role_detail),

    # Company User Role (nur für eigene Firma sichtbar)
    path('company/user-role/<int:user_id>/', views.get_company_user_role),

    # Join Requests
    path('company/joinrequests/', views.company_join_requests),
    path('company/joinrequests/<int:request_id>/approve/', views.approve_join_request),
    path('company/joinrequests/<int:request_id>/reject/', views.reject_join_request),

    #ONBOARDING
    #Send Invite
    path("onboarding/invite/send/", views.send_company_invite),
    path("onboarding/invite/accept/", views.accept_company_invite),

    #user onboarding case for registration
    path("onboarding/check_user_onboarding_case/", views.check_user_onboarding_case, name="check_user_onboarding_case"),

    
]
    


