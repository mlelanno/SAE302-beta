import sys
import random
from PySide6.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QGraphicsEllipseItem, QGraphicsRectItem, QMainWindow
from PySide6.QtGui import QPixmap, QColor, QBrush, QPainterPath, QPen
from PySide6.QtCore import QTimer, Qt, QPointF

# On importe les donnees du carrefour extraites par le script
from donnees_couleurs import DONNEES

import math

class FeuTricolore:
    def __init__(self, scene, x, y, axe):
        self.axe = axe # 1 pour Horizontal, 2 pour Vertical
        self.etat = "ROUGE"
        self.x = x
        self.y = y

        # Dessin plus joli : un petit boitier gris foncé
        self.boitier = QGraphicsRectItem(x - 10, y - 20, 20, 40)
        self.boitier.setBrush(QBrush(QColor(50, 50, 50)))
        scene.addItem(self.boitier)

        # Lumière du feu
        self.lumiere = QGraphicsEllipseItem(x - 6, y - 16, 12, 12)
        scene.addItem(self.lumiere)

        self.mettre_a_jour_couleur()

    def mettre_a_jour_couleur(self):
        if self.etat == "VERT":
            self.lumiere.setBrush(QBrush(QColor(0, 255, 0)))
            self.lumiere.setPos(0, 20) # Descendre la lumière pour le vert
        else:
            self.lumiere.setBrush(QBrush(QColor(255, 0, 0)))
            self.lumiere.setPos(0, 0) # Monter la lumière pour le rouge

class Vehicule:
    def __init__(self, scene, trajet, est_urgence=False):
        self.est_urgence = est_urgence
        self.trajet_numero = trajet['numero']

        # Le vehicule est un simple rectangle
        self.rect = QGraphicsRectItem(-10, -5, 20, 10)

        if self.est_urgence:
            self.rect.setBrush(QBrush(QColor("red")))
        else:
            self.rect.setBrush(QBrush(QColor("blue")))

        scene.addItem(self.rect)

        # Creer le chemin a partir des donnees extraites
        self.chemin = QPainterPath()
        for segment in trajet['segments']:
            commande = segment['commande']
            coords = segment['coordonnees']
            if commande == 'M':
                self.chemin.moveTo(coords[0], coords[1])
            elif commande == 'L':
                self.chemin.lineTo(coords[0], coords[1])
            elif commande == 'C':
                self.chemin.cubicTo(coords[0], coords[1], coords[2], coords[3], coords[4], coords[5])

        self.progression = 0.0
        self.vitesse = 0.005 if self.est_urgence else 0.002
        self.fini = False

        # Mettre la voiture au point de depart
        self.mettre_a_jour_position()

    def mettre_a_jour_position(self):
        # On recupere le point sur le chemin selon la progression (0 a 1)
        point = self.chemin.pointAtPercent(self.progression)
        angle = self.chemin.angleAtPercent(self.progression)

        self.rect.setPos(point)
        # On tourne la voiture pour qu'elle suive la route (angle negatif car Qt va a l'envers)
        self.rect.setRotation(-angle)

    def avancer(self):
        if self.fini:
            return

        # La voiture avance simplement (la logique d'arrêt est gérée dans la boucle principale)
        self.progression += self.vitesse
        if self.progression >= 1.0:
            self.progression = 1.0
            self.fini = True

        self.mettre_a_jour_position()

    def supprimer(self, scene):
        scene.removeItem(self.rect)

class Simulation(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simulation Carrefour Connecté - Projet 1ère Année")
        self.resize(1000, 700)

        self.scene = QGraphicsScene()

        # Afficher la carte en fond (le plan du carrefour)
        # L'image originale carrefour.png est utilisée, on la redimensionne pour qu'elle corresponde au SVG
        # Le chemin est modifié pour utiliser assets au lieu de ../assets afin d'être exécutable depuis la racine
        image_fond = QPixmap("assets/carrefour.png").scaled(1770, 1120)
        if not image_fond.isNull():
            self.scene.addPixmap(image_fond)

        self.vue = QGraphicsView(self.scene)
        self.vue.setRenderHint(self.vue.renderHints()) # Mode simple
        self.setCentralWidget(self.vue)

        # Ajuster la vue pour voir tout le carrefour
        self.vue.fitInView(0, 0, 1770, 1120, Qt.KeepAspectRatio)

        self.vehicules = []

        # Timer pour animer les voitures
        self.timer_animation = QTimer()
        self.timer_animation.timeout.connect(self.animer)
        self.timer_animation.start(30) # 30 ms

        # Ajouter les feux tricolores
        self.feux = []
        # Positions ajustées d'après les numéros sur le plan (coordonnées des petits boîtiers dessinés sur la carte)
        self.feux.append(FeuTricolore(self.scene, 560, 560, axe=1))   # Feu Ouest
        self.feux.append(FeuTricolore(self.scene, 1230, 780, axe=1))  # Feu Est
        self.feux.append(FeuTricolore(self.scene, 930, 410, axe=2))   # Feu Nord
        self.feux.append(FeuTricolore(self.scene, 820, 985, axe=2))   # Feu Sud

        self.cycle_feux = 1 # 1 = Horizontal Vert, 2 = Vertical Vert
        self.timer_feux = QTimer()
        self.timer_feux.timeout.connect(self.changer_feux)
        self.timer_feux.start(5000) # Changer de feux toutes les 5 secondes
        self.changer_feux() # Initialiser

        # Timer pour ajouter de nouvelles voitures
        self.timer_ajout = QTimer()
        self.timer_ajout.timeout.connect(self.ajouter_vehicule)
        self.timer_ajout.start(2000) # Toutes les 2 secondes

    def changer_feux(self, urgence_axe=None):
        if urgence_axe:
            self.cycle_feux = urgence_axe
            self.timer_feux.start(5000) # Redémarrer le timer normal
        else:
            self.cycle_feux = 2 if self.cycle_feux == 1 else 1

        for feu in self.feux:
            if feu.axe == self.cycle_feux:
                feu.etat = "VERT"
            else:
                feu.etat = "ROUGE"
            feu.mettre_a_jour_couleur()

    def ajouter_vehicule(self):
        trajets = DONNEES['trajets']
        trajet_choisi = random.choice(trajets)

        # 10% de chance d'avoir un véhicule d'urgence
        est_urgence = (random.random() < 0.1)

        nouveau_vehicule = Vehicule(self.scene, trajet_choisi, est_urgence)
        self.vehicules.append(nouveau_vehicule)

    def animer(self):
        # 1. Gestion anti-collision très simple :
        # Si une voiture est trop proche d'une autre devant elle ou dans le carrefour, elle s'arrête
        voitures_a_arreter = set()
        for i, v1 in enumerate(self.vehicules):
            if v1.fini: continue
            for j, v2 in enumerate(self.vehicules):
                if i == j or v2.fini: continue

                # Calculer la distance entre v1 et v2
                pos1 = v1.rect.pos()
                pos2 = v2.rect.pos()
                distance = math.hypot(pos1.x() - pos2.x(), pos1.y() - pos2.y())

                if distance < 40: # Distance de sécurité
                    # Si trop proche, celui qui a la progression la plus faible s'arrête
                    if v1.progression < v2.progression:
                        voitures_a_arreter.add(v1)
                    else:
                        voitures_a_arreter.add(v2)

        # 2. Verifier s'il y a un vehicule d'urgence dans le carrefour et forcer les feux
        urgence_en_cours = False
        axe_urgence = None
        for v in self.vehicules:
            if v.est_urgence and not v.fini:
                urgence_en_cours = True
                # Déterminer l'axe de l'urgence basé sur son point de départ
                if v.trajet_numero in [1, 2, 3, 4, 5, 6]: # Ouest et Est -> Axe Horizontal 1
                    axe_urgence = 1
                elif v.trajet_numero in [7, 8, 9, 10, 11, 12]: # Nord et Sud -> Axe Vertical 2
                    axe_urgence = 2
                break

        if urgence_en_cours and axe_urgence:
            self.changer_feux(urgence_axe=axe_urgence)

        # 3. Faire avancer toutes les voitures en leur disant s'il y a une urgence
        for v in self.vehicules:
            # On vérifie aussi si on est au rouge
            doit_sarreter = False

            # Arrêt pour anti-collision
            if v in voitures_a_arreter:
                doit_sarreter = True

            # Arrêt au feu rouge en vérifiant si la voiture est dans une "zone d'arrêt"
            # On définit une zone juste avant les feux où les voitures doivent s'arrêter au rouge
            pos = v.rect.pos()
            dans_zone_arret = False

            # Vérifications très simples basées sur la position (X,Y) sur la carte
            if v.trajet_numero in [1,2,3]: # Ouest vers le reste
                if 500 < pos.x() < 560: dans_zone_arret = True
            elif v.trajet_numero in [4,5,6]: # Est vers le reste
                if 1240 < pos.x() < 1300: dans_zone_arret = True
            elif v.trajet_numero in [7,8,9]: # Nord vers le reste
                if 350 < pos.y() < 410: dans_zone_arret = True
            elif v.trajet_numero in [10,11,12]: # Sud vers le reste
                if 985 < pos.y() < 1045: dans_zone_arret = True

            if dans_zone_arret:
                axe_vehicule = 1 if v.trajet_numero in [1,2,3,4,5,6] else 2
                if axe_vehicule != self.cycle_feux: # Si notre axe est au rouge
                    doit_sarreter = True

            if doit_sarreter:
                # On force la voiture à ne pas avancer ce tour-ci
                pass
            else:
                v.avancer()

        # 4. Supprimer les voitures arrivees
        vehicules_restants = []
        for v in self.vehicules:
            if v.fini:
                v.supprimer(self.scene)
            else:
                vehicules_restants.append(v)
        self.vehicules = vehicules_restants

if __name__ == "__main__":
    app = QApplication(sys.argv)
    fenetre = Simulation()
    fenetre.show()
    sys.exit(app.exec())
