from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import authentication_classes, permission_classes
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action

from django.contrib.auth import authenticate
from django.db import IntegrityError
from django.utils import timezone
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist

import logging
import base64
import traceback

from .permissions import ComponentAccessPermission
from .models import User, PricingPlan, Component, TeamUser, TeamComponents, CompanyComponents, Team  # <-- Importiert dein Custom User + PricingPlan
from .serializers import *

from rest_framework import viewsets, status, permissions
from rest_framework.views import APIView

from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)

from .utils import send_company_verification_email
from .utils import is_blocked_domain
from .utils import send_company_invite_mail

# -------------------------------------------------------------------------------
# AUTH

@api_view(['POST'])
def auth_login(request):
    """
    Loggt einen existierenden Benutzer ein und gibt einen Token zurück.
    """
    # 1) Benutzer via username/password authentifizieren
    user = authenticate(
        username=request.data.get('username'),
        password=request.data.get('password')
    )
    
    if user is None:
        return Response(
            {"detail": "Username or password incorrect"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # 2) Wir haben bereits den Benutzer (user). Du könntest nun auf user.email zugreifen
    #    Falls du unbedingt nochmals via E-Mail aus der DB holen willst (nicht nötig), dann so:
    #
    # try:
    #     user_in_db = User.objects.get(email=user.email)
    # except User.DoesNotExist:
    #     return Response({"detail": "User does not exist for this email"}, status=status.HTTP_404_NOT_FOUND)
    #
    # Da authenticate(...) schon einen gültigen User liefert, ersparen wir uns diesen Schritt.
    user_in_db = user

    # 3) Token generieren oder abrufen
    token, created = Token.objects.get_or_create(user=user_in_db)

    # 4) Rückgabe
    return Response({
        "token": token.key,
        "user": {
            "userid": user_in_db.id,
            "username": user_in_db.username,
            "email": user_in_db.email,
            "first_name": user_in_db.first_name,
            "last_name": user_in_db.last_name,
            "companyid": user_in_db.companyid_id,       # Falls user_in_db.companyid ist ein FK
            "pricingplanid": user_in_db.pricingplanid_id,
            "professionid": user_in_db.professionid
        }
    })

@api_view(['POST'])
def auth_signup(request):
    """
    Registriert einen neuen Benutzer und gibt den Token + User-Daten zurück.
    Blockiert Freemail-Domains und setzt keine companyid.
    """
    try:
        data = request.data
        email = data.get('email', '').lower()
        username = data.get('username', '')

        # 1) Blockierte Domain prüfen
        if is_blocked_domain(extract_main_domain(email)):
            return Response(
                {"error": "Bitte verwende eine geschäftliche E-Mail-Adresse."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2) Existiert E-Mail oder Username bereits?
        if User.objects.filter(username=username).exists():
            return Response(
                {"error": "A user with this username already exists."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if User.objects.filter(email=email).exists():
            return Response(
                {"error": "A user with this email already exists."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3) PricingPlan validieren (optional)
        pricingplanid = data.get("pricingplanid")
        if pricingplanid and not PricingPlan.objects.filter(pricingplanid=pricingplanid).exists():
            return Response(
                {"error": f"Invalid pricingplanid: {pricingplanid}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4) User erstellen
        new_user = User.objects.create(
            username=username,
            email=email,
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
            pricingplanid_id=pricingplanid,
            professionid=data.get('professionid'),
            is_superuser=False,
            is_staff=False,
            is_active=True,
            date_joined=timezone.now()
        )
        new_user.set_password(data['password'])
        new_user.save()

        # 5) Token erstellen
        token = Token.objects.create(user=new_user)

        return Response({
            "token": token.key,
            "user": {
                "username": new_user.username,
                "email": new_user.email,
                "first_name": new_user.first_name,
                "last_name": new_user.last_name,
                "companyid": new_user.companyid_id,
                "pricingplanid": new_user.pricingplanid_id,
                "professionid": new_user.professionid
            }
        }, status=status.HTTP_201_CREATED)

    except IntegrityError as e:
        if User.objects.filter(username=request.data.get('email')).exists():
            return Response(
                {"error": "A user with this email already exists."},
                status=status.HTTP_400_BAD_REQUEST
            )
        logger.exception("IntegrityError during user creation")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except Exception as e:
        logger.exception("Error in auth_signup")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def auth_validate_token(request):
    # Log all headers
    logger.debug("Request Headers:")
    for header, value in request.headers.items():
        logger.debug(f"{header}: {value}")
        print(f"{header}: {value}")

    # Jetzt wird request.user vom CustomUser-Modell stammen,
    # das in settings.py via AUTH_USER_MODEL definiert ist.
    return Response(f"passed for {request.user.email}")



# -------------------------------------------------------------------------------
# COMPONENT

@api_view(['POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def create_component(request):
    print("Received data:")
    for key, value in request.data.items():
        print(f"{key}: {value}")

    try:
        # 1) Base64-Daten dekodieren für componentppt
        ppt_data = request.data['ComponentPPT']  # kommt vom Frontend
        ppt_bytes = base64.b64decode(ppt_data)

        # 2) Auch ComponentPreview dekodieren (falls vorhanden)
        preview_data = request.data.get('ComponentPreview', None)
        preview_bytes = base64.b64decode(preview_data) if preview_data else b''

        # 3) Kopie von request.data erstellen, Binärdaten ersetzen
        data = request.data.copy()
        data['ComponentPPT'] = ppt_bytes
        data['ComponentPreview'] = preview_bytes

        print(f"Decoded ComponentPPT size: {len(ppt_bytes)}")
        print(f"Decoded ComponentPreview size: {len(preview_bytes)}")

        # 4) Neue Komponente anlegen
        #    Achte auf die Feldnamen aus deiner neuen models.py.
        #    Wir nutzen request.user als User-Objekt.
        component = Component.objects.create(
            componentname=data['ComponentName'],
            componentdescription=data.get('ComponentDescription', ''),
            componentppt=data['ComponentPPT'],
            componentpreview=data.get('ComponentPreview', b''),
            componentpublic=data['ComponentPublic'],
            userid=request.user,  # neuer ForeignKey auf dein User-Modell
            componentheight=data.get('ComponentHeight'),
            componentwidth=data.get('ComponentWidth')
        )

        # 5) Antwort senden
        return Response({
            'componentid': component.componentid,
            'componentname': component.componentname,
        }, status=status.HTTP_201_CREATED)

    except Exception as ex:
        traceback_str = traceback.format_exc()
        print("Exception occurred:", traceback_str)
        return Response({"error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated, ComponentAccessPermission])
def get_component_by_ID(request, pk):
    """
    Gibt ein einzelnes Component-Objekt anhand seiner ID (pk) zurück,
    sofern der Benutzer Zugriff hat (ComponentAccessPermission).
    """
    try:
        # 1) Component anhand der primary key (pk) aus DB holen
        component = Component.objects.get(pk=pk)
        
        # 2) Serialisieren
        serializer = ComponentSerializer(component)
        
        # 3) Erfolgs-Response mit den Daten
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Component.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as ex:
        return Response({"error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_user_components_all(request):
    """
    Gibt alle Komponenten zurück, auf die der aktuelle Benutzer Zugriff hat.
    - Öffentlich (componentpublic=True)
    - Gehört dem aktuellen Benutzer (userid = request.user)
    - Zugewiesen an ein Team, in dem der User Mitglied ist
    - Zugewiesen an die Firma, bei der der User Mitglied ist
    """
    try:
        # 1) Alle Team-IDs, in denen der User Mitglied ist
        user_teams = TeamUser.objects.filter(userid=request.user).values_list('teamid', flat=True)
        
        # 2) Alle Component-IDs, die diesen Teams zugewiesen sind
        team_component_ids = TeamComponents.objects.filter(teamid__in=user_teams).values_list('componentid', flat=True)
        
        # 3) Alle Component-IDs der Firma (Company), sofern der User eine companyid hat
        company_component_ids = []
        if request.user.companyid:  # Falls user in einer Firma ist
            company_component_ids = CompanyComponents.objects.filter(
                companyid=request.user.companyid
            ).values_list('componentid', flat=True)
        
        # 4) Jetzt kombinieren wir die Bedingung (OR-Verknüpfung):
        #    - Komponente ist public
        #    - Komponente gehört dem User
        #    - Komponente ist in team_component_ids
        #    - Komponente ist in company_component_ids
        components = Component.objects.filter(
            Q(userid=request.user) |
            Q(pk__in=team_component_ids) |
            Q(componentdefault=True) | 
            Q(componentpublic=True)
            #Q(pk__in=company_component_ids)
        ).distinct()
        
        # 5) Serialisieren und zurückgeben
        serializer = ComponentSerializer(components, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except Exception as ex:
        return Response({"error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_user_components_my_components(request):
    """
    Liefert alle Komponenten, die der aktuell angemeldete Benutzer SELBST erstellt hat
    (d. h. `userid == request.user`).

    Endpoint‑Vorschlag:  /api/components/my/
    """
    try:
        components = Component.objects.filter(userid=request.user)
        serializer = ComponentSerializer(components, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except Exception as ex:
        # In der Praxis lieber geloggte Tracebacks + generische Fehlermeldung
        return Response({"error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_user_components_favorites(request):
    """
    /api/components/favorites/
    Gibt alle Komponenten zurück, die der Benutzer als Favorit markiert hat.
    """
    favorites_qs = Component.objects.filter(
        componentfavorite__userid=request.user   #  Default‑related‑name
    ).distinct()

    serializer = ComponentSerializer(favorites_qs, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST', 'DELETE'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def toggle_favorite(request, component_id):
    """
    POST    → Component als Favorit anlegen
    DELETE  → Favorit löschen
    """
    try:
        component = Component.objects.get(pk=component_id)

        if request.method == 'POST':
            favorite, created = ComponentFavorite.objects.get_or_create(
                userid=request.user,
                componentid=component
            )
            ser = ComponentFavoriteSerializer(favorite)
            return Response(ser.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

        elif request.method == 'DELETE':
            ComponentFavorite.objects.filter(
                userid=request.user,
                componentid=component
            ).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

    except Component.DoesNotExist:
        return Response({'error': 'Component not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_components_default(request):
    """
    Gibt alle Komponenten zurück, die als *Default* markiert sind
    (`componentdefault=True`).

    Endpoint‑Vorschlag:  /user/get_components_default/
    """
    components = Component.objects.filter(componentdefault=True)
    serializer = ComponentSerializer(components, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_components_public(request):
    """
    Liefert alle Komponenten, die als öffentlich markiert sind
    (`componentpublic=True`).

    Empfohlene URL:  /user/get_components_public/
    """
    components = Component.objects.filter(componentpublic=True)
    serializer = ComponentSerializer(components, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(['DELETE'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def delete_component(request, component_id):
    """
    Löscht die Komponente (component_id).
    Nur der User, dem die Komponente gehört (userid), darf löschen.
    """
    user = request.user

    # 1) Prüfen, ob die Komponente existiert
    try:
        component = Component.objects.get(pk=component_id)
    except Component.DoesNotExist:
        return Response(
            {"error": f"Component with ID={component_id} does not exist."},
            status=status.HTTP_404_NOT_FOUND
        )

    # 2) Berechtigung prüfen: Nur der Eigentümer (component.userid) darf löschen
    if component.userid != user:
        return Response(
            {"detail": "Forbidden: You are not the owner of this component."},
            status=status.HTTP_403_FORBIDDEN
        )

    # 3) Löschen der Komponente
    component.delete()
    return Response(
        {"detail": f"Component {component_id} was successfully deleted."},
        status=status.HTTP_204_NO_CONTENT
    )



# -------------------------------------------------------------------------------
# TEAM

@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_user_teams_all(request):
    """
    Gibt alle Teams zurück, in denen der aktuelle Benutzer Mitglied ist.
    """
    try:
        # 1) Über TeamUser die Team-IDs finden, in denen der User Mitglied ist.
        user_team_ids = TeamUser.objects.filter(userid=request.user).values_list('teamid', flat=True)

         # 2) Teams absteigend nach updated_at
        teams = Team.objects.filter(
            pk__in=user_team_ids
        ).order_by('-updated_at')

        # 3) Serialisieren und zurückgeben
        serializer = TeamSerializer(teams, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except Exception as ex:
        return Response({"error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_user_teams_all_details(request):
    """
    Gibt alle Teams zurück, in denen der aktuelle Benutzer Mitglied ist,
    inklusive Zusatzinformationen:
      - Owner (Vor- und Nachname)
      - Anzahl Mitglieder
      - Anzahl zugewiesener Komponenten
    """
    try:
        # 1) Teams bestimmen, in denen der User Mitglied ist
        user_team_ids = TeamUser.objects.filter(userid=request.user).values_list('teamid', flat=True)

         # 2) Teams absteigend nach updated_at
        teams = Team.objects.filter(
            pk__in=user_team_ids
        ).order_by('-updated_at')

        # 3) Mit dem neuen Details-Serializer serialisieren
        serializer = TeamDetailsSerializer(teams, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except Exception as ex:
        return Response({"error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

@api_view(['POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def create_team(request):
    serializer = TeamCreateSerializer(data=request.data)
    if serializer.is_valid():
        try:
            team_instance = Team(
                teamname=serializer.validated_data.get('teamname'),
                companyid=serializer.validated_data.get('companyid', None),
                creatoruserid=request.user
            )
            team_instance.save()

            # 1) Hol dir eine TeamRole aus der DB (z. B. "Owner"), 
            #    oder lege sie an, falls noch nicht existiert
            owner_role, _ = TeamRole.objects.get_or_create(
                rolename='Owner',
                defaults={
                    'perm_add_people': True,
                    'perm_remove_people': True,
                    'perm_change_role': True,
                    'perm_remove_component': True,
                }
            )

            # 2) TeamUser-Objekt erstellen (User ist Owner)
            TeamUser.objects.create(
                teamid=team_instance,
                userid=request.user,
                teamrole=owner_role  # <-- statt teamroleofuser
            )

            # 3) Antwort ans Frontend
            response_data = {
                "teamid": team_instance.teamid,
                "teamname": team_instance.teamname,
                "creatoruserid": team_instance.creatoruserid.id,
                "companyid": team_instance.companyid.id if team_instance.companyid else None
            }
            return Response(response_data, status=status.HTTP_201_CREATED)
        except Exception as ex:
            return Response({"error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_users_in_team(request, team_id):
    """
    Gibt alle Benutzer zurück, die in einem bestimmten Team (team_id) Mitglied sind.
    Dazu werden die TeamUser-Einträge gefiltert und mit TeamUserSerializer 
    serialisiert, der auch die User-Daten enthält.
    """
    try:
        team_users = TeamUser.objects.filter(teamid=team_id)
        
        # Optional: Prüfen, ob das Team existiert oder ob der anfragende User berechtigt ist.
        # Beispiel: Nur zurückgeben, wenn der anfragende User selbst im Team ist, etc.
        if not team_users.exists():
            return Response({"detail": "No users found or invalid team_id"}, status=status.HTTP_404_NOT_FOUND)

        serializer = TeamUserSerializer(team_users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except Exception as ex:
        return Response({"error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])  # Optional
@permission_classes([IsAuthenticated])  # Optional
def get_all_roles(request):
    """
    Gibt alle Rollen (TeamRole) mit ihren jeweiligen Permissions (perm_add_people etc.) zurück.
    """
    try:
        roles = TeamRole.objects.all()
        serializer = TeamRoleSerializer(roles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as ex:
        return Response({"error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_users_by_company(request):
    """
    Gibt alle Benutzer aus derselben Firma wie der anfragende User zurück.
    Optional: Filterung via 'search' Query-Parameter
    Beispiel: GET /api/company/users/?search=john
    Neu: Begrenzung auf max. 5 Treffer.
    """
    try:
        if not request.user.companyid:
            return Response(
                {"detail": "You are not associated with a company."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 1) Grund-QuerySet
        users_qs = User.objects.filter(companyid=request.user.companyid)

        # 2) Optional: Filter (Suche nach Vor-/Nachname, Email, etc.)
        search_term = request.query_params.get('search', '').strip()
        if search_term:
            users_qs = users_qs.filter(
                Q(first_name__icontains=search_term) |
                Q(last_name__icontains=search_term) |
                Q(username__icontains=search_term) |
                Q(email__icontains=search_term)
            )

        # 3) Ergebnis auf max. 5 Datensätze einschränken
        users_qs = users_qs[:5]

        # 4) Serialisieren
        serializer = UserSearchSerializer(users_qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except Exception as ex:
        return Response({"error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_users_by_company_but_not_team(request):
    """
    Gibt alle Benutzer aus derselben Firma wie der anfragende User zurück,
    die noch nicht in einem bestimmten Team sind.
    
    Query-Parameter:
      - search:  optional (Vor-/Nachname, E-Mail, Username durchsuchen)
      - team_id: optional (Team-ID, aus dem bereits vorhandene User ausgeschlossen werden sollen)
      
    Begrenzung auf max. 5 Treffer.
    """
    try:
        if not request.user.companyid:
            return Response(
                {"detail": "You are not associated with a company."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 1) Grund-QuerySet: alle User in derselben Firma
        users_qs = User.objects.filter(companyid=request.user.companyid)

        # 2) Falls ein team_id gegeben ist, User dieses Teams ausschließen
        team_id = request.query_params.get('team_id', None)
        if team_id:
            from django.db.models import Q
            from server.models import TeamUser  # Passe den Pfad an dein Projekt an
            
            # IDs aller Benutzer im angegebenen Team
            user_ids_in_team = TeamUser.objects.filter(teamid=team_id).values_list('userid', flat=True)
            # ausschließen
            users_qs = users_qs.exclude(pk__in=user_ids_in_team)

        # 3) Optional: Filter (Suche nach Vor-/Nachname, Email, etc.)
        search_term = request.query_params.get('search', '').strip()
        if search_term:
            users_qs = users_qs.filter(
                Q(first_name__icontains=search_term) |
                Q(last_name__icontains=search_term) |
                Q(username__icontains=search_term) |
                Q(email__icontains=search_term)
            )

        # 4) Ergebnis auf max. 5 Datensätze einschränken
        users_qs = users_qs[:5]

        # 5) Serialisieren
        serializer = UserSearchSerializer(users_qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except Exception as ex:
        return Response({"error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@api_view(['POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def add_component_to_team(request, team_id, component_id):
    """
    Fügt die Komponente (component_id) dem Team (team_id) hinzu.
    Nur zulässig, wenn der anfragende User selbst Mitglied in diesem Team ist.
    """
    try:
        # 1) Prüfen, ob der User Mitglied im Team ist
        is_member = TeamUser.objects.filter(userid=request.user, teamid=team_id).exists()
        if not is_member:
            return Response({"detail": "Forbidden: You are not a member of this team."},
                            status=status.HTTP_403_FORBIDDEN)

        # 2) Team und Komponente abrufen
        try:
            team = Team.objects.get(pk=team_id)
        except Team.DoesNotExist:
            return Response({"error": f"Team with ID={team_id} does not exist."},
                            status=status.HTTP_404_NOT_FOUND)

        try:
            component = Component.objects.get(pk=component_id)
        except Component.DoesNotExist:
            return Response({"error": f"Component with ID={component_id} does not exist."},
                            status=status.HTTP_404_NOT_FOUND)

        # 3) Prüfen, ob das Pairing schon existiert
        if TeamComponents.objects.filter(teamid=team, componentid=component).exists():
            return Response({"detail": "This component is already in the team."},
                            status=status.HTTP_200_OK)  # oder 409 Conflict

        # 4) TeamComponents-Eintrag erstellen
        TeamComponents.objects.create(teamid=team, componentid=component)

        return Response({
            "detail": f"Component {component_id} was added to Team {team_id}."
        }, status=status.HTTP_201_CREATED)

    except Exception as ex:
        return Response({"error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


@api_view(['DELETE'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def remove_component_from_team(request, team_id, component_id):
    """
    Entfernt die Komponente (component_id) aus dem Team (team_id).
    Nur zulässig, wenn der anfragende User im Team ist UND
    seine Teamrolle perm_remove_component = True hat.
    """
    try:
        # 1) TeamUser-Eintrag abrufen, um Rolle zu bekommen
        try:
            user_in_team = TeamUser.objects.get(userid=request.user, teamid=team_id)
        except TeamUser.DoesNotExist:
            return Response(
                {"detail": "Forbidden: You are not a member of this team."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 2) Rolle prüfen
        user_role = user_in_team.teamrole
        if not user_role or not user_role.perm_remove_component:
            return Response(
                {"detail": "Forbidden: Your role doesn't allow removing components."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 3) TeamComponents-Eintrag suchen und löschen
        pairing_qs = TeamComponents.objects.filter(teamid=team_id, componentid=component_id)
        if not pairing_qs.exists():
            return Response(
                {"detail": "Component not found in this team."},
                status=status.HTTP_404_NOT_FOUND
            )

        pairing_qs.delete()
        return Response({
            "detail": f"Component {component_id} was removed from Team {team_id}."
        }, status=status.HTTP_200_OK)

    except Exception as ex:
        return Response({"error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_team_components(request, team_id):
    """
    Gibt alle Komponenten zurück, die einem bestimmten Team (team_id) zugewiesen sind,
    sofern der anfragende User Mitglied in diesem Team ist.
    """
    try:
        # 1) Prüfen, ob der User Mitglied im Team ist
        is_member = TeamUser.objects.filter(userid=request.user, teamid=team_id).exists()
        if not is_member:
            return Response(
                {"detail": "Forbidden: You are not a member of this team."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 2) Alle Component-IDs, die diesem Team zugewiesen sind
        team_component_ids = TeamComponents.objects.filter(teamid=team_id).values_list('componentid', flat=True)

        # 3) Komponenten abrufen
        components = Component.objects.filter(pk__in=team_component_ids).distinct()

        # 4) Serialisieren und zurückgeben
        serializer = ComponentSerializer(components, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except Exception as ex:
        return Response({"error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_component_teams(request, component_id):
    """
    Liefert alle Teams zurück, die die Komponente (component_id) enthalten
    und in denen der anfragende User Mitglied ist.
    """
    user = request.user

    # 1) Prüfen, ob die Komponente existiert
    try:
        component = Component.objects.get(pk=component_id)
    except Component.DoesNotExist:
        return Response(
            {"error": f"Component with ID={component_id} does not exist."},
            status=status.HTTP_404_NOT_FOUND
        )

    # 2) Ermitteln, in welchen Teams der User Mitglied ist
    user_team_ids = TeamUser.objects.filter(
        userid=user
    ).values_list('teamid_id', flat=True)

    # 3) Ermitteln, welche dieser Teams die Komponente haben
    team_components = TeamComponents.objects.filter(
        componentid=component,
        teamid_id__in=user_team_ids
    ).select_related('teamid')

    # 4) Response-Daten aufbereiten
    teams_data = [
        {
            "team_id": tc.teamid.teamid,
            "team_name": tc.teamid.teamname,
            "company_id": tc.teamid.companyid_id,
            "updated_at": tc.teamid.updated_at,
        }
        for tc in team_components
    ]

    return Response(teams_data, status=status.HTTP_200_OK)

# views.py (Ergänzung)

@api_view(['POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def add_user_to_team(request, team_id):
    """
    Fügt den in request.data['user_id'] angegebenen Benutzer zum Team (team_id) hinzu.
    Erfordert, dass der anfragende User im Team ist und perm_add_people=True besitzt.
    Optional: teamrole_id – ansonsten wird die Rolle 'Member' vergeben.
    """
    try:
        # 1) Serializer validieren
        serializer = AddUserToTeamSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_id_to_add = serializer.validated_data['user_id']
        teamrole_id = serializer.validated_data.get('teamrole_id', None)

        # 2) Prüfen, ob der anfragende User im Team ist
        try:
            requester = TeamUser.objects.get(userid=request.user, teamid=team_id)
        except TeamUser.DoesNotExist:
            return Response(
                {"detail": "You are not a member of this team."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 3) Prüfen, ob der anfragende User berechtigt ist
        if not requester.teamrole or not requester.teamrole.perm_add_people:
            return Response(
                {"detail": "Your role doesn't allow adding team members."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 4) Team und User laden
        try:
            team = Team.objects.get(pk=team_id)
        except Team.DoesNotExist:
            return Response({"detail": "Team does not exist."}, status=status.HTTP_404_NOT_FOUND)

        try:
            user_to_add = User.objects.get(pk=user_id_to_add)
        except User.DoesNotExist:
            return Response({"detail": "User does not exist."}, status=status.HTTP_404_NOT_FOUND)

        # 5) Prüfen, ob der User bereits im Team ist
        if TeamUser.objects.filter(teamid=team, userid=user_to_add).exists():
            return Response({"detail": "User is already in the team."}, status=status.HTTP_409_CONFLICT)

        # 6) Teamrolle bestimmen
        if teamrole_id:
            try:
                role = TeamRole.objects.get(pk=teamrole_id)
            except TeamRole.DoesNotExist:
                return Response({"detail": "Role does not exist."}, status=status.HTTP_404_NOT_FOUND)
        else:
            try:
                role = TeamRole.objects.get(rolename='User')
            except TeamRole.DoesNotExist:
                return Response({"detail": "Default role 'User' not found."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 7) Benutzer zum Team hinzufügen
        TeamUser.objects.create(teamid=team, userid=user_to_add, teamrole=role)

        return Response({
            "detail": f"User {user_to_add.id} was added to Team {team_id} with role '{role.rolename}'."
        }, status=status.HTTP_201_CREATED)

    except Exception as ex:
        return Response({"error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def remove_user_from_team(request, team_id):
    """
    Entfernt den Benutzer (user_id) aus dem angegebenen Team,
    falls der anfragende Benutzer die Berechtigung hat.
    """
    try:
        user_id_to_remove = request.data.get('user_id', None)
        if not user_id_to_remove:
            return Response({"detail": "Missing user_id"}, status=status.HTTP_400_BAD_REQUEST)

        # 1) Ist der anfragende User Mitglied des Teams?
        try:
            requester = TeamUser.objects.get(userid=request.user, teamid=team_id)
        except TeamUser.DoesNotExist:
            return Response(
                {"detail": "You are not a member of this team."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 2) Berechtigung prüfen
        if not requester.teamrole or not requester.teamrole.perm_remove_people:
            return Response(
                {"detail": "Your role doesn't allow removing team members."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 3) Team & Ziel-User abrufen
        try:
            team = Team.objects.get(pk=team_id)
        except Team.DoesNotExist:
            return Response({"detail": "Team does not exist."}, status=status.HTTP_404_NOT_FOUND)

        try:
            target_user = User.objects.get(pk=user_id_to_remove)
        except User.DoesNotExist:
            return Response({"detail": "User does not exist."}, status=status.HTTP_404_NOT_FOUND)

        # 4) Prüfen, ob dieser User im Team ist
        try:
            team_user = TeamUser.objects.get(teamid=team, userid=target_user)
        except TeamUser.DoesNotExist:
            return Response({"detail": "User is not a member of this team."}, status=status.HTTP_404_NOT_FOUND)

        # 5) Optional: Owner darf nicht entfernt werden
        if team_user.teamrole.rolename == 'Owner':
            return Response({"detail": "You cannot remove the Owner of the team."}, status=status.HTTP_403_FORBIDDEN)

        # 6) Eintrag löschen
        team_user.delete()

        return Response({
            "detail": f"User {target_user.id} was removed from Team {team_id}."
        }, status=status.HTTP_200_OK)

    except Exception as ex:
        return Response({"error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_team_role(request, team_id):
    """
    Gibt zurück, welche Rolle und welche Permissions der angemeldete User
    in dem Team (team_id) hat.
    """
    user = request.user

    # 1) Prüfen, ob das Team existiert
    try:
        team = Team.objects.get(pk=team_id)
    except Team.DoesNotExist:
        return Response(
            {"error": f"Team with ID={team_id} does not exist."},
            status=status.HTTP_404_NOT_FOUND
        )

    # 2) Prüfen, ob der User Mitglied in diesem Team ist
    try:
        team_user = TeamUser.objects.select_related('teamrole').get(
            userid=user,
            teamid=team
        )
    except TeamUser.DoesNotExist:
        return Response(
            {"detail": "Forbidden: You are not a member of this team."},
            status=status.HTTP_403_FORBIDDEN
        )

    # 3) Rolle und Permissions abrufen
    role = team_user.teamrole  # Kann None sein, falls keine Rolle gesetzt
    if role is None:
        # Falls keine Rolle vergeben, senden wir Standard-Antwort ohne Rechte
        return Response(
            {
                "team_id": team.teamid,
                "team_name": team.teamname,
                "role": None,
                "permissions": {
                    "add_people": False,
                    "remove_people": False,
                    "change_role": False,
                    "remove_component": False
                }
            },
            status=status.HTTP_200_OK
        )

    # 4) Falls Rolle vorhanden, Permissions auslesen
    permissions = {
        "add_people": role.perm_add_people,
        "remove_people": role.perm_remove_people,
        "change_role": role.perm_change_role,
        "remove_component": role.perm_remove_component
    }

    # 5) Zusammenstellung der Rückgabe
    data = {
        "team_id": team.teamid,
        "team_name": team.teamname,
        "role": {
            "role_id": role.teamroleid,
            "role_name": role.rolename
        },
        "permissions": permissions
    }
    return Response(data, status=status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def change_user_role(request, team_id, user_id):
    """
    Ändert die Rolle (teamrole) eines Users (user_id) im Team (team_id),
    sofern der anfragende User selbst Mitglied im Team ist und 
    die Berechtigung perm_change_role hat.
    Erwartet im Request-Body:
      {
        "teamrole_id": <neue_Rollen-ID>
      }
    """

    try:
        # 1) Prüfen, ob der anfragende User Mitglied im Team ist
        try:
            requester_membership = TeamUser.objects.get(
                userid=request.user, 
                teamid_id=team_id
            )
        except TeamUser.DoesNotExist:
            return Response(
                {"detail": "Forbidden: You are not a member of this team."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 2) Prüfen, ob der requester die Berechtigung zum Rollenwechsel hat
        if not requester_membership.teamrole or not requester_membership.teamrole.perm_change_role:
            return Response(
                {"detail": "Forbidden: You do not have permission to change roles in this team."},
                status=status.HTTP_403_FORBIDDEN
            )

        # 3) Prüfen, ob der zu ändernde User ebenfalls Mitglied im Team ist
        try:
            target_membership = TeamUser.objects.get(
                userid_id=user_id,
                teamid_id=team_id
            )
        except TeamUser.DoesNotExist:
            return Response(
                {"detail": f"User {user_id} is not a member of team {team_id}."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 4) Neue Rollen-ID aus dem Request-Body lesen
        new_role_id = request.data.get('teamrole_id')
        if new_role_id is None:
            return Response(
                {"error": "Missing 'teamrole_id' in request body."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 5) Prüfen, ob die angegebene Rolle existiert
        try:
            new_role = TeamRole.objects.get(pk=new_role_id)
        except TeamRole.DoesNotExist:
            return Response(
                {"error": f"TeamRole with ID={new_role_id} does not exist."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 6) Rolle im TeamUser-Objekt anpassen und speichern
        target_membership.teamrole = new_role
        target_membership.save()

        # 7) Serialisieren und zurückgeben
        serializer = TeamUserSerializer(target_membership)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except Exception as ex:
        return Response({"error": str(ex)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_all_company_roles(request):
    roles = CompanyRole.objects.all()
    return Response(CompanyRoleSerializer(roles, many=True).data)


@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_company_role_detail(request, role_id):
    role = get_object_or_404(CompanyRole, pk=role_id)
    return Response(CompanyRoleSerializer(role).data)


@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_company_user_role(request, user_id):
    # Stelle sicher, dass der angefragte Nutzer zur selben Firma gehört
    try:
        my_company = CompanyUserRole.objects.get(user=request.user).company
    except CompanyUserRole.DoesNotExist:
        return Response({'detail': 'Du gehörst keiner Firma an'}, status=status.HTTP_403_FORBIDDEN)

    try:
        user_role = CompanyUserRole.objects.get(user__id=user_id, company=my_company)
    except CompanyUserRole.DoesNotExist:
        return Response({'detail': 'Kein Zugriff auf diesen Nutzer'}, status=status.HTTP_403_FORBIDDEN)

    return Response(CompanyUserRoleSerializer(user_role).data)


@api_view(['GET', 'POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def company_join_requests(request):
    try:
        my_company = CompanyUserRole.objects.get(user=request.user).company
    except CompanyUserRole.DoesNotExist:
        return Response({'detail': 'Du gehörst keiner Firma an'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        is_approver = CompanyUserRole.objects.filter(
            user=request.user,
            company=my_company,
            companyrole__perm_approve_requests=True
        ).exists()

        if is_approver:
            requests = CompanyJoinRequest.objects.filter(company=my_company, status='PENDING')
        else:
            requests = CompanyJoinRequest.objects.filter(user=request.user)

        return Response(CompanyJoinRequestSerializer(requests, many=True).data)

    elif request.method == 'POST':
        serializer = CompanyJoinRequestSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            # Sicherheitscheck: Der JoinRequest darf nur für die eigene Firma sein
            if serializer.validated_data['company'] != my_company:
                return Response({'detail': 'JoinRequest nur für eigene Firma erlaubt'}, status=status.HTTP_403_FORBIDDEN)

            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

@api_view(['POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def approve_join_request(request, request_id):
    req = get_object_or_404(CompanyJoinRequest, pk=request_id)

    try:
        my_company = CompanyUserRole.objects.get(user=request.user).company
    except CompanyUserRole.DoesNotExist:
        return Response({'detail': 'Du gehörst keiner Firma an'}, status=status.HTTP_403_FORBIDDEN)

    if req.company != my_company:
        return Response({'detail': 'Kein Zugriff auf andere Firmen'}, status=status.HTTP_403_FORBIDDEN)

    has_permission = CompanyUserRole.objects.filter(
        user=request.user,
        company=my_company,
        companyrole__perm_approve_requests=True
    ).exists()

    if not has_permission:
        return Response({'detail': 'Keine Berechtigung'}, status=status.HTTP_403_FORBIDDEN)

    req.status = 'APPROVED'
    req.save()

    member_role = CompanyRole.objects.get(rolename='User')
    CompanyUserRole.objects.create(
        user=req.user,
        company=req.company,
        companyrole=member_role
    )

    return Response(CompanyJoinRequestSerializer(req).data)


@api_view(['POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def reject_join_request(request, request_id):
    req = get_object_or_404(CompanyJoinRequest, pk=request_id)

    try:
        my_company = CompanyUserRole.objects.get(user=request.user).company
    except CompanyUserRole.DoesNotExist:
        return Response({'detail': 'Du gehörst keiner Firma an'}, status=status.HTTP_403_FORBIDDEN)

    if req.company != my_company:
        return Response({'detail': 'Kein Zugriff auf andere Firmen'}, status=status.HTTP_403_FORBIDDEN)

    has_permission = CompanyUserRole.objects.filter(
        user=request.user,
        company=my_company,
        companyrole__perm_approve_requests=True
    ).exists()

    if not has_permission:
        return Response({'detail': 'Keine Berechtigung'}, status=status.HTTP_403_FORBIDDEN)

    req.status = 'REJECTED'
    req.save()

    return Response(CompanyJoinRequestSerializer(req).data)


@api_view(['POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def create_company(request):
    serializer = CompanyCreateSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        company = Company.objects.create(companyname=serializer.validated_data['companyname'])
        domain = serializer.validated_data['email_domain']

        CompanyDomain.objects.create(company=company, domain=domain)

        verification = CompanyVerification.objects.create(user=request.user, company=company)
        send_company_verification_email(request.user.email, verification.token)

        return Response({
            'detail': 'Firma wurde angelegt. Bitte bestätige deine E-Mail.',
            'company': company.companyname,
            'token_sent_to': request.user.email
        }, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def verify_company_token(request, token):
    verification = get_object_or_404(CompanyVerification, token=token, used=False)

    verification.company.is_verified = True
    verification.company.save()

    verification.user.companyid = verification.company
    verification.user.save()

    owner_role = CompanyRole.objects.get(rolename='Admin')
    CompanyUserRole.objects.create(
        user=verification.user,
        company=verification.company,
        companyrole=owner_role
    )

    verification.used = True
    verification.save()

    return Response({'detail': 'Deine Firma wurde bestätigt. Du bist jetzt als Owner eingetragen.'})



@api_view(['POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def send_company_invite(request):
    user = request.user
    company = get_object_or_404(Company, pk=request.data["companyid"])

    if not CompanyUserRole.objects.filter(
        user=user,
        company=company,
        companyrole__perm_invite_users=True
    ).exists():
        return Response({"error": "Keine Berechtigung, um Nutzer einzuladen."}, status=403)

    try:
        user_role = CompanyRole.objects.get(rolename="User")
    except ObjectDoesNotExist:
        return Response({"error": "Rolle 'User' existiert nicht in CompanyRole."}, status=500)

    email = request.data["email"]
    invite_domain = extract_main_domain(email)

    if not CompanyDomain.objects.filter(company=company, domain=invite_domain).exists():
        return Response({
            "error": f"Die E-Mail-Domain '{invite_domain}' gehört nicht zur Firma '{company.companyname}'."},
            status=400
        )

    invite = CompanyInvite.objects.create(
        email=email,
        company=company,
        role=user_role,
        invited_by=user
    )

    send_company_invite_mail(invite, user)

    return Response({
        "message": "Einladung erstellt und Mail versendet.",
        "invite_token": str(invite.token)
    }, status=201)




@api_view(['POST'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def accept_company_invite(request):
    """
    Akzeptiert eine Einladung über den Token, sofern die eingeloggte E-Mail-Adresse passt.
    """
    token = request.data.get("invite_token")
    if not token:
        return Response({"error": "Kein Invite-Token übergeben."}, status=400)

    try:
        invite = CompanyInvite.objects.get(token=token, accepted=False)
    except CompanyInvite.DoesNotExist:
        return Response({"error": "Ungültiger oder bereits angenommener Token."}, status=404)

    if invite.email.lower() != request.user.email.lower():
        return Response({"error": "E-Mail-Adresse passt nicht zur Einladung."}, status=403)

    CompanyUserRole.objects.create(
        user=request.user,
        company=invite.company,
        companyrole=invite.role
    )

    invite.accepted = True
    invite.save()

    return Response({"message": "Einladung erfolgreich angenommen."}, status=200)

@api_view(['GET'])
def check_user_onboarding_case(request):
    """
    Gibt zurück, welcher Onboarding-Case auf die angegebene E-Mail zutrifft.
    Entweder über invite_token oder über E-Mail-Domain.
    """
    invite_token = request.query_params.get("invite_token", "").strip()
    email = request.query_params.get("email", "").strip().lower()

    # ✅ Fall 1: Einladung über Token
    if invite_token:
        invite = CompanyInvite.objects.filter(token=invite_token).first()
        if invite:
            return Response({
                "case": "invited_user",
                "company_name": invite.company.companyname,
                "email": invite.email
            })

    # ⛔ Wenn keine E-Mail übergeben wurde
    if not email or "@" not in email:
        return Response({"error": "Ungültige E-Mail-Adresse."}, status=status.HTTP_400_BAD_REQUEST)

    domain = extract_main_domain(email)

    # ❌ Fall 2: Blockierte Domain
    if is_blocked_domain(domain):
        return Response({"case": "blocked_domain"})

    # 🔍 Fall 3: Einladung per E-Mail gefunden
    if CompanyInvite.objects.filter(email=email).exists():
        invite = CompanyInvite.objects.filter(email=email).latest("created_at")
        return Response({
            "case": "invited_user",
            "company_name": invite.company.companyname,
            "email": invite.email
        })

    # 🏢 Fall 4: Domain gehört zu existierender Firma
    domain_entry = CompanyDomain.objects.filter(domain=domain).first()
    if domain_entry:
        return Response({
            "case": "company_domain",
            "company_name": domain_entry.company.companyname
        })

    # 🆕 Fall 5: Neue Firma anlegen
    return Response({
        "case": "new_company"
    })
