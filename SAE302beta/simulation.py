import sys
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QGraphicsView, QGraphicsScene, QMainWindow,
                               QWidget, QHBoxLayout, QPushButton, QButtonGroup)
from PySide6.QtGui import QColor, QBrush, QPainterPath, QPen, QTransform, QPainter, QPixmap
from PySide6.QtCore import QTimer, Qt
from PySide6.QtSvgWidgets import QGraphicsSvgItem
from donnees_couleurs import DONNEES

TRAFIC = "dense"
FREQUENCES = {"faible": 8, "moyen": 4, "dense": 2}  # Secondes par branche.
PAS = 0.03
LONGUEUR = 30  # Unités du dessin, pas des mètres.
LARGEUR = 15
ESPACE = 12
MAX_VIRAGES = 3  # Maximum de voitures présentes par trajet qui coupe le flux.
ORDRE = [1, 1, 1, 0, 0, 0, 1, 1, 1, 2]  # Tout droit, gauche, droite : choix de simulation.
PHASES = [
    (2, "VERT", 20),
    (2, "ORANGE", 2),
    (0, "ROUGE", 2),
    (1, "VERT", 20),
    (1, "ORANGE", 2),
    (0, "ROUGE", 2),
]
APPROCHES = [2, 2, 2, 3, 3, 3, 3, 3, 3, 2, 2, 2]
CENTRES = [3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4]
RONDS = [
    ["circle167", "circle168", "circle169"],
    ["circle195", "circle196", "circle197"],
    ["circle187", "circle188", "circle189"],
    ["circle183", "circle184", "circle185"],
]


def creer_chemin(segments):
    chemin = QPainterPath()
    for segment in segments:
        commande = segment["commande"]
        valeurs = segment["coordonnees"]
        if commande == "M":
            chemin.moveTo(valeurs[0], valeurs[1])
        elif commande == "L":
            chemin.lineTo(valeurs[0], valeurs[1])
        elif commande == "C":
            chemin.cubicTo(valeurs[0], valeurs[1], valeurs[2], valeurs[3], valeurs[4], valeurs[5])
        else:
            raise ValueError("Commande SVG inconnue : " + commande)
    return chemin


def forme_sur_chemin(chemin, distance, marge=0):
    proportion = chemin.percentAtLength(distance)
    point = chemin.pointAtPercent(proportion)
    forme = QPainterPath()
    forme.addRect(-LONGUEUR / 2 - marge, -LARGEUR / 2 - 2,
                  LONGUEUR + 2 * marge, LARGEUR + 4)
    placement = QTransform()
    placement.translate(point.x(), point.y())
    placement.rotate(-chemin.angleAtPercent(proportion))
    return placement.map(forme)


class FeuTricolore:
    def __init__(self, scene, plan, identifiants, axe):
        self.axe = axe
        self.ronds = []
        lecteur = plan.renderer()
        for identifiant in identifiants:
            cadre = lecteur.boundsOnElement(identifiant)
            cadre = lecteur.transformForElement(identifiant).mapRect(cadre)
            rond = scene.addEllipse(cadre)
            rond.setPen(QPen(Qt.PenStyle.NoPen))
            rond.setZValue(2)
            self.ronds.append(rond)

    def afficher(self, etat):
        self.etat = etat
        couleurs = {"ROUGE": "#ff3030", "ORANGE": "#ffb000", "VERT": "#00df60"}
        for indice, nom in enumerate(["ROUGE", "ORANGE", "VERT"]):
            couleur = "#78858a"
            if nom == etat:
                couleur = couleurs[nom]
            self.ronds[indice].setBrush(QBrush(QColor(couleur)))


class Vehicule:
    def __init__(self, scene, trajet, numero=0, urgence=False):
        self.numero = numero
        self.trajet = trajet
        self.distance = 0.0
        self.engage = False
        self.urgence = urgence
        self.fuyard = False  
        
        self.rect = scene.addRect(-LONGUEUR / 2, -LARGEUR / 2, LONGUEUR, LARGEUR)
        
        if urgence:
            self.rect.setBrush(QBrush(QColor("#ff1111")))
            self.rect.setPen(QPen(QColor("white"), 2))
            self.rect.setZValue(3)
        else:
            self.rect.setBrush(QBrush(QColor("#247bc0")))
            self.rect.setPen(QPen(Qt.PenStyle.NoPen))
            self.rect.setZValue(1)
            
        self.mettre_a_jour_position()

    def mettre_a_jour_position(self):
        chemin = self.trajet["chemin"]
        proportion = chemin.percentAtLength(self.distance)
        self.rect.setPos(chemin.pointAtPercent(proportion))
        self.rect.setRotation(-chemin.angleAtPercent(proportion))
        self.forme = forme_sur_chemin(chemin, self.distance)

    def supprimer(self, scene):
        scene.removeItem(self.rect)


class Simulation(QMainWindow):
    def __init__(self):
        super().__init__()
        self.trafic = TRAFIC
        self.setWindowTitle("Simulation du carrefour")
        self.resize(1100, 740)
        self.scene = QGraphicsScene()
        fichier = Path(__file__).with_name("carrefour_couleurs.svg")
        self.plan = QGraphicsSvgItem(str(fichier))
        if not self.plan.renderer().isValid():
            raise ValueError("Le plan SVG est absent ou invalide.")
        self.scene.addItem(self.plan)
        self.scene.setSceneRect(self.plan.boundingRect())
        self.vue = QGraphicsView(self.scene)
        self.vue.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.vue.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.vue.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setCentralWidget(self.vue)
        
        self.horloge = self.scene.addPixmap(QPixmap())
        self.horloge.setPos(1190, 60)
        self.horloge.setZValue(5)
        self.afficher_heure()
        
        contenu = QWidget()
        contenu.setObjectName("choix_trafic")
        contenu.setStyleSheet("QWidget#choix_trafic { background: transparent; }")
        contenu.setFixedWidth(540)
        ligne = QHBoxLayout(contenu)
        ligne.setContentsMargins(0, 0, 0, 0)
        
        self.boutons = QButtonGroup(self)
        self.boutons.setExclusive(True)
        for nom, niveau in [("Dense", "dense"), ("Moyen", "moyen"), ("Faible", "faible")]:
            bouton = QPushButton(nom)
            bouton.setMinimumHeight(40)
            bouton.setStyleSheet("font-size: 20px; color: black;")
            bouton.setCheckable(True)
            bouton.setChecked(niveau == self.trafic)
            self.boutons.addButton(bouton)
            ligne.addWidget(bouton)
            
        btn_urgence = QPushButton("🚨 Urgence")
        btn_urgence.setMinimumHeight(40)
        btn_urgence.setStyleSheet("font-size: 18px; color: white; background-color: #ff3030; font-weight: bold; border-radius: 4px;")
        btn_urgence.clicked.connect(self.declencher_urgence)
        ligne.addWidget(btn_urgence)
            
        self.boutons.buttonClicked.connect(self.changer_trafic)
        self.panneau_boutons = self.scene.addWidget(contenu)
        self.panneau_boutons.setPos(1190, 305)
        self.panneau_boutons.setZValue(5)
        
        self.vehicules = []
        self.nombre_crees = 0
        
        # NOUVEAU : Variables pour l'apparition différée de l'ambulance
        self.urgence_en_attente = False
        self.temps_spawn_urgence = 0.0
        
        self.trajets = {}
        for donnee in DONNEES["trajets"]:
            trajet = donnee.copy()
            numero = trajet["numero"]
            segments = trajet["segments"]
            debut = APPROCHES[numero - 1]
            fin = CENTRES[numero - 1]
            approche = creer_chemin(segments[:debut])
            centre = creer_chemin(segments[:fin])
            trajet["chemin"] = creer_chemin(segments)
            trajet["longueur"] = trajet["chemin"].length()
            trajet["arret"] = approche.length() - LONGUEUR / 2 - 4
            trajet["fin_centre"] = centre.length() + LONGUEUR / 2 + 4
            trajet["gauche"] = numero in [1, 4, 7, 10]
            trajet["axe"] = 2
            if numero <= 6:
                trajet["axe"] = 1
            self.trajets[numero] = trajet
            
        self.feux = []
        for indice, identifiants in enumerate(RONDS):
            axe = 2
            if indice < 2:
                axe = 1
            self.feux.append(FeuTricolore(self.scene, self.plan, identifiants, axe))
            
        self.temps = 0.0
        self.phase = 0
        self.fin_phase = PHASES[0][2]
        self.prochaines = {1: 0, 4: 0, 7: 0, 10: 0}
        self.directions = {1: 0, 4: 0, 7: 0, 10: 0}
        self.preparer_convois()
        self.timer_animation = QTimer(self)
        self.timer_animation.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer_animation.timeout.connect(self.animer)
        self.timer_animation.start(round(PAS * 1000))
        self.actualiser_feux()

    def resizeEvent(self, evenement):
        super().resizeEvent(evenement)
        QTimer.singleShot(0, self.ajuster_vue)

    def ajuster_vue(self):
        self.vue.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def changer_trafic(self, bouton):
        niveaux = {"Dense": "dense", "Moyen": "moyen", "Faible": "faible"}
        self.trafic = niveaux[bouton.text()]
        self.afficher_heure()
        for base in self.prochaines:
            self.prochaines[base] = self.temps + FREQUENCES[self.trafic]

    def declencher_urgence(self):
        # On ne fait plus spawn directement. On active l'alerte réseau et on programme le spawn dans 3 secondes.
        if not self.urgence_en_attente:
            self.urgence_en_attente = True
            self.temps_spawn_urgence = self.temps + 3.0  # Apparition dans 3 secondes

    def spawn_ambulance_physique(self):
        # La fonction qui crée véritablement l'ambulance après les 3 secondes d'alerte
        trajet_sn = self.trajets[11]  
        forme_spawn = forme_sur_chemin(trajet_sn["chemin"], 0, ESPACE)
        
        if not self.espace_occupe(forme_spawn):
            self.nombre_crees += 1
            ambulance = Vehicule(self.scene, trajet_sn, self.nombre_crees, urgence=True)
            self.vehicules.append(ambulance)
        else:
            for voiture in self.vehicules:
                if forme_spawn.intersects(voiture.forme):
                    voiture.urgence = True
                    voiture.trajet = trajet_sn
                    voiture.rect.setBrush(QBrush(QColor("#ff1111")))
                    voiture.rect.setPen(QPen(QColor("white"), 2))
                    voiture.rect.setZValue(3)
                    break

    def afficher_heure(self):
        fichiers = {"dense": "heure_08.png", "moyen": "heure_12.png", "faible": "heure_23.png"}
        fichier = Path(__file__).parent / "images" / fichiers[self.trafic]
        image = QPixmap(str(fichier))
        if image.isNull():
            raise ValueError("Image de l'heure absente : " + str(fichier))
        self.horloge.setPixmap(image.scaledToWidth(540, Qt.TransformationMode.SmoothTransformation))

    def actualiser_feux(self):
        axe, etat, duree = PHASES[self.phase]
        for feu in self.feux:
            couleur = "ROUGE"
            if feu.axe == axe:
                couleur = etat
            feu.afficher(couleur)

    def preparer_convois(self):
        self.etape = "CONVOIS"
        self.convoi = []
        axe = PHASES[self.phase][0]
        for voiture in self.vehicules:
            trajet = voiture.trajet
            proche = voiture.distance >= trajet["arret"] - MAX_VIRAGES * (LONGUEUR + ESPACE)
            if trajet["axe"] == axe and trajet["gauche"] and not voiture.engage and proche:
                self.convoi.append(voiture)

    def gerer_feux(self):
        axe, etat, duree = PHASES[self.phase]
        if etat == "VERT" and self.etape == "CONVOIS":
            for voiture in self.convoi:
                if voiture.distance < voiture.trajet["fin_centre"]:
                    return
            self.etape = "FLUX"
            self.fin_phase = self.temps + duree
        if self.temps < self.fin_phase:
            return
        if etat == "ROUGE":
            for voiture in self.vehicules:
                if voiture.engage and voiture.distance < voiture.trajet["fin_centre"]:
                    return
        self.phase = (self.phase + 1) % len(PHASES)
        self.fin_phase = self.temps + PHASES[self.phase][2]
        if PHASES[self.phase][1] == "VERT":
            self.preparer_convois()

    def espace_occupe(self, forme, voiture_ignoree=None):
        cadre = forme.boundingRect()
        for autre in self.vehicules:
            if autre is not voiture_ignoree and cadre.intersects(autre.forme.boundingRect()):
                if forme.intersects(autre.forme):
                    return True
        return False

    def ajouter_vehicule(self):
        for base in self.prochaines:
            if self.temps < self.prochaines[base]:
                continue
            numero = base + ORDRE[self.directions[base]]
            if numero == base:
                nombre = 0
                for autre in self.vehicules:
                    if autre.trajet["numero"] == base:
                        nombre += 1
                if nombre >= MAX_VIRAGES:
                    self.directions[base] = (self.directions[base] + 1) % len(ORDRE)
                    continue
            trajet = self.trajets[numero]
            if self.espace_occupe(forme_sur_chemin(trajet["chemin"], 0, ESPACE)):
                continue
            self.nombre_crees += 1
            voiture = Vehicule(self.scene, trajet, self.nombre_crees)
            self.vehicules.append(voiture)
            self.directions[base] = (self.directions[base] + 1) % len(ORDRE)
            self.prochaines[base] = self.temps + FREQUENCES[self.trafic]

    def passage_libre(self, voiture):
        if self.etape == "CONVOIS":
            return voiture in self.convoi
        return not voiture.trajet["gauche"]

    def avancer(self, voiture):
        # 1. L'alerte V2I est active dès qu'on a cliqué sur le bouton (même si l'ambulance n'est pas encore là)
        alerte_urgence = self.urgence_en_attente
        for autre in self.vehicules:
            if autre.urgence:
                alerte_urgence = True
                break

        pousse_par_urgence = voiture.fuyard
        voiture.vitesse = 250 if voiture.urgence else (150 if voiture.fuyard else 100)

        # 2. Réaction des civils à l'alerte globale
        if alerte_urgence and not voiture.urgence:
            if voiture.engage:
                # Les civils déjà dans le carrefour accélèrent pour dégager
                voiture.vitesse = 250
            else:
                # Les civils au feu rouge regardent s'il y a physiquement une ambulance derrière eux
                for autre in self.vehicules:
                    if autre.urgence and autre.trajet["numero"] == voiture.trajet["numero"] and autre.distance <= voiture.distance:
                        voiture.fuyard = True
                        pousse_par_urgence = True
                        voiture.vitesse = 150
                        
                        base = ((voiture.trajet["numero"] - 1) // 3) * 3 + 1
                        trajet_droite = self.trajets[base + 2]
                        if voiture.trajet["numero"] != trajet_droite["numero"]:
                            voiture.trajet = trajet_droite
                            voiture.mettre_a_jour_position()
                        break

        trajet = voiture.trajet
        distance = min(voiture.distance + voiture.vitesse * PAS, trajet["longueur"])
        engagement = False
        
        # 3. Franchissement de la ligne d'arrêt
        if not voiture.engage and distance > trajet["arret"]:
            axe, etat, duree = PHASES[self.phase]
            feu_vert = (axe == trajet["axe"] and etat == "VERT" and self.passage_libre(voiture))
            
            # GESTION V2I : Si l'alerte est active (même 3 secondes avant l'ambulance),
            # les feux verts sont annulés pour les civils.
            if alerte_urgence and not voiture.urgence and not pousse_par_urgence:
                feu_vert = False
                
            if voiture.urgence or pousse_par_urgence or feu_vert:
                engagement = True
            else:
                distance = trajet["arret"]
                
        # 4. Radar anti-collision
        forme = forme_sur_chemin(trajet["chemin"], distance, ESPACE)
        if self.espace_occupe(forme, voiture):
            return  
            
        voiture.distance = distance
        if engagement:
            voiture.engage = True
        voiture.mettre_a_jour_position()

    def animer(self):
        self.temps += PAS
        self.gerer_feux()
        
        # NOUVEAU : Si 3 secondes se sont écoulées depuis le clic, l'ambulance apparaît !
        if self.urgence_en_attente and self.temps >= self.temps_spawn_urgence:
            self.spawn_ambulance_physique()
            self.urgence_en_attente = False
            
        for voiture in self.vehicules:
            self.avancer(voiture)
            
        restants = []
        for voiture in self.vehicules:
            if voiture.distance >= voiture.trajet["longueur"]:
                voiture.supprimer(self.scene)
            else:
                restants.append(voiture)
        self.vehicules = restants
        self.ajouter_vehicule()
        self.actualiser_feux()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    fenetre = Simulation()
    fenetre.show()
    sys.exit(app.exec())