# myapp/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
import uuid


class Company(models.Model):
    """
    Repräsentiert ein Unternehmen (Firma).
    Wird ggf. bei Löschung übergeordneter Datensätze
    zugeordneten Objekten entfernt (z.B. Teams).
    """
    companyid = models.AutoField(db_column='CompanyID', primary_key=True)
    companyname = models.TextField(db_column='CompanyName')
    is_verified = models.BooleanField(db_column='CompanyIsVerified', default=False)
    created_at = models.DateTimeField(db_column='CompanyCreatedTimeStamp', auto_now_add=True)
    
    class Meta:
        managed = True
        db_table = 'Company'
    
    def __str__(self):
        return self.companyname
    
class CompanyDomain(models.Model):
    """
    Eine Domain, die einer Firma zugeordnet ist (z.B. firma.de).
    Wird verwendet für Domain-Matching und Beitrittslogik.
    """
    domainid = models.AutoField(db_column='DomainID', primary_key=True)
    company = models.ForeignKey(
        'Company',
        on_delete=models.CASCADE,
        related_name='domains',
        db_column='CompanyID'
    )
    domain = models.CharField(db_column='Domain', max_length=255, unique=True)

    class Meta:
        db_table = 'CompanyDomain'
        managed = True

    def __str__(self):
        return f"{self.domain} → {self.company.companyname}"


class CompanyVerification(models.Model):
    """
    Tokenbasierte Verifizierung für neu registrierte Firmen.
    Nach Klick auf den Link wird die Firma aktiviert und
    der User als Owner eingetragen.
    """
    verificationid = models.AutoField(db_column='VerificationID', primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column='UserID'
    )
    company = models.ForeignKey(
        'Company',
        on_delete=models.CASCADE,
        db_column='CompanyID'
    )
    token = models.UUIDField(db_column='VerificationToken', default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(db_column='VerificationCreated', auto_now_add=True)
    used = models.BooleanField(db_column='VerificationUsed', default=False)

    class Meta:
        db_table = 'CompanyVerification'
        managed = True

    def __str__(self):
        return f"{self.user.email} → {self.company.companyname}"



class PricingPlan(models.Model):
    """
    Repräsentiert ein Preismodell (PricingPlan).
    Löschen wir einen PricingPlan, werden die User,
    die darauf verweisen, auf Null gesetzt (SET_NULL).
    """
    pricingplanid = models.AutoField(db_column='PricingPlanID', primary_key=True)
    pricingplanname = models.TextField(db_column='PricingPlanName')
    pricingplandescription = models.TextField(db_column='PricingPlanDescription', blank=True, null=True)
    pricingplanmonthlypriceeur = models.FloatField(db_column='PricingPlanMonthlyPriceEUR', blank=True, null=True)
    
    class Meta:
        managed = True
        db_table = 'PricingPlan'
    
    def __str__(self):
        return self.pricingplanname


class User(AbstractUser):
    """
    Custom User Model, ersetzt das Standard-Django-User-Modell.
    Erbt alle Felder von AbstractUser (username, email, password etc.)
    + zusätzliche Felder (companyid, pricingplanid, professionid).
    """
    companyid = models.ForeignKey(
        Company, 
        on_delete=models.SET_NULL,   # Wenn die Company gelöscht wird, wird der User nicht gelöscht,
                                     # aber sein companyid-Feld wird null.
        db_column='companyid',
        blank=True, 
        null=True
    )

    pricingplanid = models.ForeignKey(
        PricingPlan, 
        on_delete=models.SET_NULL,   # Löschen wir das PricingPlan-Objekt, wird das Feld auf null gesetzt.
        db_column='pricingplanid',
        blank=True, 
        null=True
    )

    professionid = models.IntegerField(
        db_column='professionid',
        blank=True, 
        null=True
    )

    class Meta:
        # db_table = 'auth_user'  # Falls du einen bestimmten Tabellennamen möchtest
        managed = True
    
    def __str__(self):
        return self.username

class InviteToken(models.Model):
    """
    Dient dazu, neue Benutzer per E-Mail einzuladen und automatisch ihrer Firma zuzuordnen.
    - token: UUID4-Token, einmalig pro Einladung.
    - email: Zieladresse, z.B. "anna@acme.com".
    - company: Firma, zu der eingeladen wird.
    - created_by: User (muss is_company_admin=True sein).
    - used: Boolean-Flag, ob Token bereits eingelöst wurde.
    - created_at, used_at: Timestamps zur Nachverfolgung.
    """
    inviteid = models.AutoField(db_column='InviteID', primary_key=True)
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    email = models.EmailField(db_column='Email')
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        db_column='CompanyID',
        related_name='invite_tokens'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column='CreatedByUserID',
        related_name='created_invites'
    )
    used = models.BooleanField(
        db_column='Used',
        default=False,
        help_text="Wird nach erfolgreicher Aktivierung auf True gesetzt."
    )
    created_at = models.DateTimeField(
        db_column='CreatedAt',
        auto_now_add=True
    )
    used_at = models.DateTimeField(
        db_column='UsedAt',
        blank=True,
        null=True
    )

    class Meta:
        managed = True
        db_table = 'InviteToken'

    def __str__(self):
        status = "✓" if self.used else "✗"
        return f"[{status}] Invite {self.email} → {self.company.companyname}"
    

class Component(models.Model):
    """
    Repräsentiert eine Komponente (z.B. ein Shape oder PPT-Element).
    Optional kann ein Component einem User gehören,
    wobei DO_NOTHING bedeutet, dass die Komponente bestehen bleibt,
    falls ein User gelöscht wird.
    """
    componentid = models.AutoField(db_column='ComponentID', primary_key=True)
    componentname = models.TextField(db_column='ComponentName')
    componentdescription = models.TextField(db_column='ComponentDescription', blank=True, null=True)
    componentppt = models.BinaryField(db_column='ComponentPPT', blank=True, null=True)
    componentpreview = models.BinaryField(db_column='ComponentPreview', blank=True, null=True)
    componentpublic = models.BooleanField(db_column='ComponentPublic', default=False)
    componentdefault = models.BooleanField(db_column='ComponentDefault', default=False)

    userid = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.DO_NOTHING,  # Beim Löschen des Users bleibt die Komponente bestehen
        db_column='UserID',
        blank=True, 
        null=True
    )

    componentwidth = models.DecimalField(db_column='ComponentWidth', max_digits=10, decimal_places=2, blank=True, null=True)
    componentheight = models.DecimalField(db_column='ComponentHeight', max_digits=10, decimal_places=2, blank=True, null=True)

    class Meta:
        managed = True
        db_table = 'Component'

    def __str__(self):
        return self.componentname


class Team(models.Model):
    """
    Repräsentiert ein Team innerhalb einer Firma.
    Wird die zugehörige Firma (Company) gelöscht, löschen wir auch das Team (CASCADE).
    Der Ersteller (creatoruserid) wird ebenfalls per CASCADE gelöscht, wenn der User entfällt.
    """
    teamid = models.AutoField(db_column='TeamID', primary_key=True)
    teamname = models.TextField(db_column='TeamName')
    
    companyid = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,   # Löscht man die Company, verschwinden alle zugehörigen Teams.
        db_column='CompanyID',
        blank=True,
        null=True
    )

    creatoruserid = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,   # Löscht man den User, entfällt auch das Team (oder man ändert auf SET_NULL, falls gewünscht).
        db_column='CreatorUserID',
        blank=True,
        null=True
    )

    updated_at = models.DateTimeField(
        db_column='UpdatedAt',
        auto_now=True,
        help_text="Wird bei jedem Speichern auf die aktuelle Zeit gesetzt."
    )

    class Meta:
        managed = True
        db_table = 'Team'

    def __str__(self):
        return self.teamname

class TeamRole(models.Model):
    teamroleid = models.AutoField(db_column='TeamRoleID', primary_key=True)
    rolename = models.TextField(db_column='RoleName', unique=True)

    # Neue Spalten für Berechtigungen
    perm_add_people = models.BooleanField(db_column='PermAddPeople', default=False)
    perm_remove_people = models.BooleanField(db_column='PermRemovePeople', default=False)
    perm_change_role = models.BooleanField(db_column='PermChangeRole', default=False)
    perm_remove_component = models.BooleanField(db_column='PermRemoveComponent', default=False)

    class Meta:
        managed = True
        db_table = 'TeamRole'

    def __str__(self):
        return self.rolename

class TeamUser(models.Model):
    """
    Verknüpfungstabelle zwischen Team und User.
    on_delete=CASCADE bedeutet: 
    - Wenn das Team gelöscht wird, werden die Zuordnungen ebenfalls entfernt.
    - Wenn der User gelöscht wird, ebenfalls.
    """
    teamuserid = models.AutoField(db_column='TeamUserID', primary_key=True)
    teamid = models.ForeignKey(
        Team, 
        on_delete=models.CASCADE,
        db_column='TeamID'
    )
    userid = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        db_column='UserID'
    )
    
    teamrole = models.ForeignKey(
        TeamRole,
        on_delete=models.SET_NULL,
        db_column='TeamRoleID',
        blank=True,
        null=True
    )


    class Meta:
        managed = True
        db_table = 'TeamUser'


class TeamComponents(models.Model):
    """
    Verknüpfungstabelle: Welches Team hat welche Komponenten?
    on_delete=CASCADE: Löscht man das Team oder die Komponente,
    werden diese Zuordnungen ebenfalls gelöscht.
    """
    teamcomponentsid = models.AutoField(db_column='TeamComponentsID', primary_key=True)
    teamid = models.ForeignKey(
        Team, 
        on_delete=models.CASCADE,
        db_column='TeamID'
    )
    componentid = models.ForeignKey(
        Component, 
        on_delete=models.CASCADE,
        db_column='ComponentID'
    )

    class Meta:
        managed = True
        db_table = 'TeamComponents'


class CompanyComponents(models.Model):
    """
    Verknüpfungstabelle: Welche Firma (Company) hat Zugriff auf welche Komponenten?
    on_delete=CASCADE löscht die Zuordnung,
    wenn entweder die Firma oder die Komponente entfällt.
    """
    companycomponentsid = models.AutoField(db_column='CompanyComponentsID', primary_key=True)
    companyid = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE,
        db_column='CompanyID'
    )
    componentid = models.ForeignKey(
        Component, 
        on_delete=models.CASCADE,
        db_column='ComponentID'
    )

    class Meta:
        managed = True
        db_table = 'CompanyComponents'


# myapp/models.py
class ComponentFavorite(models.Model):
    """
    Welche User haben welche Komponenten als Favorit markiert?
    """
    componentfavoriteid = models.AutoField(db_column='ComponentFavoriteID', primary_key=True)
    userid = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column='UserID'
    )
    componentid = models.ForeignKey(
        Component,
        on_delete=models.CASCADE,
        db_column='ComponentID'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = 'ComponentFavorite'
        unique_together = ('userid', 'componentid')  # ein Favorite je User/Component

    def __str__(self):
        return f"{self.userid} ♥ {self.componentid}"


class CompanyRole(models.Model):
    """
    Definiert eine Rolle auf Firmen-Ebene, z.B. Owner, Admin, Member.
    Jede Rolle kann spezifische Berechtigungen haben.
    """
    companyroleid = models.AutoField(primary_key=True)
    rolename       = models.CharField(max_length=100, unique=True)
    # Beispiel-Permissions – erweitere nach Bedarf
    perm_invite_users     = models.BooleanField(default=False)
    perm_approve_requests = models.BooleanField(default=False)
    perm_manage_settings  = models.BooleanField(default=False)
    perm_remove_users  = models.BooleanField(default=False)
    perm_change_user_role  = models.BooleanField(default=False)

    class Meta:
        db_table = 'CompanyRole'
        managed  = True

    def __str__(self):
        return self.rolename


class CompanyUserRole(models.Model):
    """
    Verknüpft User und Company mit einer CompanyRole.
    Ein User kann hier genau eine Rolle pro Company haben.
    """
    companyuserroleid        = models.AutoField(primary_key=True)

    user      = models.ForeignKey(settings.AUTH_USER_MODEL,
                                  on_delete=models.CASCADE,
                                  related_name='company_roles')
    company   = models.ForeignKey(Company,
                                  on_delete=models.CASCADE,
                                  related_name='user_roles')
    companyrole      = models.ForeignKey(CompanyRole,
                                  on_delete=models.PROTECT,
                                  related_name='user_assignments')
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'CompanyUserRole'
        unique_together = ('user', 'company')
        managed = True

    def __str__(self):
        return f"{self.user.email} as {self.role.rolename} @ {self.company.companyname}"


class CompanyJoinRequest(models.Model):
    """
    Ein Request, mit dem ein Nutzer beitreten möchte, 
    wenn seine E-Mail-Domain schon zu einer Company gehört.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    requestid = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='join_requests'
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='join_requests'
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='PENDING'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CompanyInvite(models.Model):
    """
    Eine Einladung für einen User, einer Firma beizutreten.
    """
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    email = models.EmailField()
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    role = models.ForeignKey(CompanyRole, on_delete=models.PROTECT)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted = models.BooleanField(default=False)

    class Meta:
        db_table = "CompanyInvite"

    def __str__(self):
        return f"{self.email} → {self.company.companyname}"