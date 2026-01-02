# myapp/serializers.py

from rest_framework import serializers
from .models import *
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from .utils import extract_main_domain 

BANNED_DOMAINS = ['gmail.com', 'yahoo.com', 'gmx.de', 'hotmail.com']

class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = '__all__'


class PricingPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = PricingPlan
        fields = '__all__'


class UserSerializer(serializers.ModelSerializer):
    """
    Dein Custom User-Serializer, enthält alle Felder 
    (z.B. username, email, first_name, etc. + companyid, pricingplanid, professionid).
    """
    class Meta:
        model = User
        fields = '__all__'
        # Oder wenn du nicht alle Felder willst, kannst du eine Liste angeben,
        # z.B. ['id', 'username', 'email', 'companyid', 'pricingplanid', 'professionid'] 


class ComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Component
        fields = '__all__'


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = '__all__'


class TeamUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamUser
        fields = '__all__'


class TeamComponentsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamComponents
        fields = '__all__'


class CompanyComponentsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyComponents
        fields = '__all__'


class TeamRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamRole
        fields = '__all__'

#---------------------- Inividual Request Serializers -------------------------------

class TeamDetailsSerializer(serializers.ModelSerializer):
    # Besitzer (Owner) → Vor- und Nachname aus dem User-Modell
    owner_first_name = serializers.CharField(source='creatoruserid.first_name', read_only=True)
    owner_last_name = serializers.CharField(source='creatoruserid.last_name', read_only=True)

    # Anzahl Mitglieder → Aus TeamUser ermitteln
    member_count = serializers.SerializerMethodField()

    # Anzahl Komponenten → Aus TeamComponents ermitteln
    component_count = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = [
            'teamid',
            'teamname',
            'owner_first_name',
            'owner_last_name',
            'member_count',
            'component_count',
        ]

    def get_member_count(self, obj):
        # obj ist das aktuelle Team
        return TeamUser.objects.filter(teamid=obj).count()

    def get_component_count(self, obj):
        return TeamComponents.objects.filter(teamid=obj).count()
    
class TeamCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ['teamname', 'companyid']  # falls du noch mehr Felder erlauben möchtest, füge sie hinzu

    def create(self, validated_data):
        # Die Logik, um ein Team zu erstellen, landet hier.
        # Den creatoruserid fügen wir z.B. in der View hinzu.
        return Team.objects.create(**validated_data)
    
from rest_framework import serializers
from .models import TeamUser, User

class TeamUserSerializer(serializers.ModelSerializer):
    """
    Ermöglicht das Lesen und Setzen der Rolle:
      - Lesen: Nested (teamrole_data)
      - Schreiben: PK (teamrole)
    """
    # Nur zum Lesen: Zeigt die Rolle mitsamt Permissions an
    teamrole_data = TeamRoleSerializer(source='teamrole', read_only=True)

    # Zum Schreiben: Man gibt eine teamrole-ID, um das FK-Feld zu setzen
    teamrole = serializers.PrimaryKeyRelatedField(
        queryset=TeamRole.objects.all(),
        write_only=True,
        required=False
    )

    # Beispiel: Du willst eventuell auch User-Daten ausgeben
    user = serializers.SerializerMethodField()

    class Meta:
        model = TeamUser
        fields = [
            'teamuserid',
            'teamid',
            'user',
            'teamrole',       # ← PK zum Schreiben
            'teamrole_data',  # ← Nested zum Lesen
        ]

    def get_user(self, obj):
        user_obj = obj.userid
        return {
            'userid': user_obj.id,
            'username': user_obj.username,
            'email': user_obj.email,
            'first_name': user_obj.first_name,
            'last_name': user_obj.last_name,
        }

    # Optional: create / update Methoden überschreiben, wenn du Sonderlogik brauchst
    # Django REST Framework übernimmt jedoch das Setzen des FK i. d. R. automatisch.

# serializers.py
from rest_framework import serializers
from .models import User

class UserSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
        ]


class AddUserToTeamSerializer(serializers.Serializer):
    """
    Nimmt user_id und optional teamrole_id entgegen.
    """
    user_id = serializers.IntegerField()
    teamrole_id = serializers.IntegerField(required=False)

    def validate_teamrole_id(self, value):
        """
        Optional: Prüfen, ob die angegebene Rolle existiert.
        """
        if value:
            if not TeamRole.objects.filter(pk=value).exists():
                raise serializers.ValidationError(f"TeamRole with ID={value} does not exist.")
        return value
    

class ComponentFavoriteSerializer(serializers.ModelSerializer):
    """
    Serializer für Favoriten‑Einträge.
    Achtung: Primärschlüssel heißt jetzt componentfavoriteid.
    """
    class Meta:
        model = ComponentFavorite
        fields = [
            'componentfavoriteid',  
            'userid',
            'componentid',
            'created_at',
        ]
        read_only_fields = ['componentfavoriteid', 'created_at']

        
class CompanyRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyRole
        fields = '__all__'


class CompanyUserRoleSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all())
    companyrole = serializers.PrimaryKeyRelatedField(queryset=CompanyRole.objects.all())

    class Meta:
        model = CompanyUserRole
        fields = '__all__'


class CompanyJoinRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyJoinRequest
        fields = ['requestid', 'user', 'company', 'status', 'created_at', 'updated_at']
        read_only_fields = ['requestid', 'user', 'status', 'created_at', 'updated_at']

    def validate_company(self, company):
        """
        Verhindert, dass ein User einen JoinRequest für eine Firma stellt,
        der er bereits angehört.
        """
        user = self.context['request'].user
        if CompanyUserRole.objects.filter(user=user, company=company).exists():
            raise serializers.ValidationError("Du bist bereits Mitglied dieser Firma.")
        return company
    


class CompanyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['companyname']

    def validate(self, data):
        user = self.context['request'].user
        email_domain = extract_main_domain(user.email)

        if email_domain in BANNED_DOMAINS:
            raise serializers.ValidationError("Private E-Mail-Domains wie gmail.com sind nicht erlaubt.")

        if CompanyDomain.objects.filter(domain=email_domain).exists():
            raise serializers.ValidationError("Diese Domain ist bereits einer Firma zugeordnet.")

        data['email_domain'] = email_domain
        return data
    
class CompanyInviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyInvite
        fields = "__all__"
        read_only_fields = ["token", "created_at", "accepted"]