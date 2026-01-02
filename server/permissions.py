# myapp/permissions.py

from rest_framework.permissions import BasePermission
from .models import Component, TeamUser, TeamComponents, CompanyComponents

class ComponentAccessPermission(BasePermission):
    """
    Prüft, ob ein Benutzer auf eine bestimmte Komponente zugreifen darf.
    1) Muss eingeloggt sein.
    2) Erlaubt Zugriff, wenn:
       - Die Komponente öffentlich ist.
       - Der User der Ersteller (component.userid) ist.
       - Der User in einem Team ist, das die Komponente besitzt (TeamComponents).
       - Der User Mitglied einer Firma ist, der die Komponente zugewiesen ist (CompanyComponents).
    """
    def has_permission(self, request, view):
        # 1) Ist der Benutzer eingeloggt?
        if not request.user.is_authenticated:
            print("Component Access Permission Error: User is not authenticated.")
            return False
        
        # 2) Hole die Komponente anhand 'pk' (ID) aus der URL
        component_id = view.kwargs.get('pk')
        if not component_id:
            return False
        
        component = Component.objects.filter(pk=component_id).first()
        if not component:
            print("Component Access Permission Error: Component does not exist.")
            return False
        
        # 3) Ist die Komponente öffentlich?
        if component.componentpublic:
            print("Component Access Permission: Public Component.")
            return True
        
        # 4) Ist der anfragende Benutzer der Ersteller der Komponente?
        #    component.userid ist ein ForeignKey auf User
        if component.userid and component.userid == request.user:
            print("Component Access Permission: Component Creator.")
            return True
        
        # 5) Ist der Benutzer Mitglied eines Teams, dem die Komponente zugewiesen ist?
        #    - TeamUser verknüpft user und team
        #    - TeamComponents verknüpft team und component
        user_teams = TeamUser.objects.filter(userid=request.user).values_list('teamid', flat=True)
        if TeamComponents.objects.filter(teamid__in=user_teams, componentid=component).exists():
            print("Component Access Permission: Team Member.")
            return True
        
        # 6) Ist der Benutzer Mitglied einer Firma (Company), der die Komponente zugewiesen ist?
        #    - user.companyid => die Company des Users
        #    - CompanyComponents => verknüpft Company und Component
        if request.user.companyid:
            if CompanyComponents.objects.filter(
                companyid=request.user.companyid,
                componentid=component
            ).exists():
                print("Component Access Permission: Company Member.")
                return True
        
        # 7) Wenn keiner der obigen Checks greift, verweigern wir den Zugriff
        return False
