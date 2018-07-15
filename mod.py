import bs
import random
import math
import bsUtils
import bsBomb
import bsVector
import bsSpaz

def bsGetAPIVersion():
    # see bombsquadgame.com/apichanges
    return 4

def bsGetGames():
    return [LandGrab]

class PlayerSpaz_Grab(bs.PlayerSpaz):

    def dropBomb(self):
        """
        Tell the spaz to drop one of his bombs, and returns
        the resulting bomb object.
        If the spaz has no bombs or is otherwise unable to
        drop a bomb, returns None.
        
        Overridden for Land Grab: 
        -Add condition for mineTimeout,
        -make it create myMine instead of regular mine
        -set this spaz's last mine time to current time
        -Don't decrement LandMineCount.  We'll set to 0 when spaz double-punches.
        """
        t = bs.getGameTime()
        if ((self.landMineCount <= 0 or t-self.lastMine < self.mineTimeout) and self.bombCount <= 0) or self.frozen: return
        p = self.node.positionForward
        v = self.node.velocity

        if self.landMineCount > 0:
            droppingBomb = False
            #self.setLandMineCount(self.landMineCount-1) #Don't decrement mine count. Unlimited mines.
            if t - self.lastMine < self.mineTimeout:
                return #Last time we dropped  mine was too short ago. Don't drop another one.
            else:
                self.lastMine = t
                self.node.billboardCrossOut = True
                bs.gameTimer(self.mineTimeout,bs.WeakCall(self.unCrossBillboard))
                bomb = myMine(pos=(p[0],p[1] - 0.0,p[2]),
                           vel=(v[0],v[1],v[2]),
                           bRad=self.blastRadius,
                           sPlay=self.sourcePlayer,
                           own=self.node).autoRetain()
                self.getPlayer().gameData['mines'].append(bomb)
        elif self.dropEggs:
            if len(self.getPlayer().gameData['bots']) > 0 : return #Only allow one snowman at a time.
            droppingBomb = True
            bomb = Egg(position=(p[0],p[1] - 0.0,p[2]), sourcePlayer=self.sourcePlayer,owner=self.node).autoRetain()
            
        else:
            droppingBomb = True
            bombType = self.bombType

            bomb = bs.Bomb(position=(p[0],p[1] - 0.0,p[2]),
                       velocity=(v[0],v[1],v[2]),
                       bombType=bombType,
                       blastRadius=self.blastRadius,
                       sourcePlayer=self.sourcePlayer,
                       owner=self.node).autoRetain()

        if droppingBomb:
            self.bombCount -= 1
            bomb.node.addDeathAction(bs.WeakCall(self.handleMessage,bsSpaz._BombDiedMessage()))
            if not self.eggsHatch:
                bomb.hatch = False
            else:
                bomb.hatch = True
        self._pickUp(bomb.node)

        for c in self._droppedBombCallbacks: c(self,bomb)
        
        return bomb
    def unCrossBillboard(self):
        if self.node.exists():
            self.node.billboardCrossOut = False
    def onPunchPress(self):
        """
        Called to 'press punch' on this spaz;
        used for player or AI connections.
        Override for land grab: catch double-punch to switch bombs!
        """
        if not self.node.exists() or self.frozen or self.node.knockout > 0.0: return
        
        if self.punchCallback is not None:
            self.punchCallback(self)
        t = bs.getGameTime()
        self._punchedNodes = set() # reset this..
        ########This catches punches and switches between bombs and mines
        #if t - self.lastPunchTime < 500:
        if self.landMineCount < 1:
            self.landMineCount = 1
            bs.animate(self.node,"billboardOpacity",{0:0.0,100:1.0,400:1.0})
        else:
            self.landMineCount = 0
            bs.animate(self.node,"billboardOpacity",{0:1.0,400:0.0})
        if t - self.lastPunchTime > self._punchCooldown:
            self.lastPunchTime = t
            self.node.punchPressed = True
            if not self.node.holdNode.exists():
                bs.gameTimer(100,bs.WeakCall(self._safePlaySound,self.getFactory().swishSound,0.8))
    def handleMessage(self, m):
        #print m.sourcePlayer
        if isinstance(m, bs.HitMessage):
            #print m.sourcePlayer.getName()
            if not self.node.exists():
                return True
            if m.sourcePlayer != self.getPlayer():
                return True
            else:
                super(self.__class__, self).handleMessage(m)
        else:
            super(self.__class__, self).handleMessage(m)
class myMine(bs.Bomb):
    #reason for the mine class is so we can intercept messages.
    def __init__(self,pos,vel,bRad,sPlay,own):
        bs.Bomb.__init__(self,position=pos,velocity=vel,bombType='landMine',blastRadius=bRad,sourcePlayer=sPlay,owner=own)
        self.isHome = False
        self.died = False
        self.activated = False
        self.defRad = self.getActivity().claimRad
        self.rad = 0.0# Will set to self.getActivity().settings['Claim Size'] when arming
        #Don't do this until mine arms
        self.zone = None 
        fm = bs.getSharedObject('footingMaterial')
        materials = getattr(self.node,'materials')
        if not fm in materials:
            setattr(self.node,'materials',materials + (fm,))
    
    def handleMessage(self,m):
        if isinstance(m,bsBomb.ArmMessage): 
            self.arm()#This is all the  main bs.Bomb does.  All below is extra
            self.activateArea()
        elif isinstance(m, bs.HitMessage):
            #print m.hitType, m.hitSubType
            if self.isHome: return True
            if m.sourcePlayer == self.sourcePlayer:
                return True #I think this should stop mines from exploding due to self activity or chain reactions?.
            if not self.activated: return True
            else:
                super(self.__class__, self).handleMessage(m)
        elif isinstance(m,bsBomb.ImpactMessage):
            if self.isHome: return True #Never explode the home bomb.
            super(self.__class__, self).handleMessage(m)
        elif isinstance(m,bs.DieMessage):
            if self.isHome: return True #Home never dies (even if player leaves, I guess...)
            if self.exists() and not self.died:
                self.died = True
                self.rad = 0.0
                if self.zone.exists():
                    bs.animateArray(self.zone,'size',1,{0:[2*self.rad],1:[0]})
                self.zone = None
            super(self.__class__, self).handleMessage(m)
        else:
            super(self.__class__, self).handleMessage(m)
    
    def activateArea(self):
        mineOK = False
        if self.exists():
            r = self.defRad
            fudge = self.getActivity().minOverlap #This is the minimum overlap to join owner's territory (not used to check enemy overlap)
            p1 = self.node.position
            self.node.maxSpeed = 0.0 #We don't want mines moving around. They could leave their zone.
            self.damping = 100
        #First, confirm that this mine "touches" owner's mines
        if self.sourcePlayer.exists():
            for m in self.sourcePlayer.gameData['mines']:
                if m.exists() and not m.died:
                    if m.rad != 0: #Don't check un-activated mines
                        p2 = m.node.position
                        diff = (bs.Vector(p1[0]-p2[0],0.0,p1[2]-p2[2]))
                        dist = (diff.length())
                        if dist < (m.rad + r)-fudge: #We check m.rad just in case it's somehow different. However, this probably shouldn't happen. Unless I change gameplay later.
                            mineOK = True #mine adjoins owner's territory. Will set to false if it also adjoin's enemy though.
                            break #Get out of the loop
        takeovers = []
        if mineOK:
            for p in self.getActivity().players:
                if not p is self.sourcePlayer:
                    if p.exists():
                        for m in p.gameData['mines']:
                            if m.rad != 0.0: #Don't check un-activated mines
                                p2 = m.node.position
                                diff = (bs.Vector(p1[0]-p2[0],0.0,p1[2]-p2[2]))
                                dist = (diff.length())
                                if dist < m.rad + r: #We check m.rad just in case it's somehowdifferent. However, this probably shouldn't happen. Unless I change gameplay later.
                                    mineOK = False
                                    takeovers = []
                                    break

        #If we made it to here and mineOK is true, we can activate.  Otherwise, we'll flash red and die.
        self.zone = bs.newNode('locator',attrs={'shape':'circle','position':self.node.position,'color':self.sourcePlayer.color,'opacity':0.5,'drawBeauty':False,'additive':True})
        bs.animateArray(self.zone,'size',1,{0:[0.0],150:[2*r]}) #Make circle at the default radius to show players where it would go if OK
        if mineOK or self.isHome:
            self.activated = True
            self.rad = r #Immediately set this mine's radius
        else: #mine was not OK
            keys = {0:(1,0,0),49:(1,0,0),50:(1,1,1),100:(0,1,0)}
            bs.animateArray(self.zone,'color',3,keys,loop=True)
            bs.gameTimer(800, bs.WeakCall(self.handleMessage, bs.DieMessage()), repeat=False)
        #Takeovers didn't work so well.  Very confusing.
        #if len(takeovers) > 0:
        #    #Flash it red and kill it
        #    for m in takeovers:
        #        if m.exists():
        #            if not m._exploded:
        #                if not m.died:
        #                    keys = {0:(1,0,0),49:(1,0,0),50:(1,1,1),100:(0,1,0)}
        #                    if m.zone.exists():
        #                        bs.animateArray(m.zone,'color',3,keys,loop=True)
        #                    bs.gameTimer(800, bs.WeakCall(m.handleMessage, bs.DieMessage()), repeat=False)
    def _handleHit(self,m):
        #This one is overloaded to prevent chaining of explosions
        isPunch = (m.srcNode.exists() and m.srcNode.getNodeType() == 'spaz')

        # normal bombs are triggered by non-punch impacts..  impact-bombs by all impacts
        if not self._exploded and not isPunch or self.bombType in ['impact','landMine']:
            # also lets change the owner of the bomb to whoever is setting us off..
            # (this way points for big chain reactions go to the person causing them)
            if m.sourcePlayer not in [None]:
                #self.sourcePlayer = m.sourcePlayer

                # also inherit the hit type (if a landmine sets off by a bomb, the credit should go to the mine)
                # the exception is TNT.  TNT always gets credit.
                #if self.bombType != 'tnt':
                #    self.hitType = m.hitType
                #    self.hitSubType = m.hitSubType
                pass
            bs.gameTimer(100+int(random.random()*100),bs.WeakCall(self.handleMessage,bsBomb.ExplodeMessage()))
        self.node.handleMessage("impulse",m.pos[0],m.pos[1],m.pos[2],
                                m.velocity[0],m.velocity[1],m.velocity[2],
                                m.magnitude,m.velocityMagnitude,m.radius,0,m.velocity[0],m.velocity[1],m.velocity[2])

        if m.srcNode.exists():
            pass
            #print 'FIXME HANDLE KICKBACK ON BOMB IMPACT'
            # bs.nodeMessage(m.srcNode,"impulse",m.srcBody,m.pos[0],m.pos[1],m.pos[2],
            #                     -0.5*m.force[0],-0.75*m.force[1],-0.5*m.force[2])
    def _handleImpact(self,m):
        #This is overridden so that we can keep from exploding due to own player's activity.
        node,body = bs.getCollisionInfo("opposingNode","opposingBody")
        # if we're an impact bomb and we came from this node, don't explode...
        # alternately if we're hitting another impact-bomb from the same source, don't explode...
        
        try: nodeDelegate = node.getDelegate() #This could be a bomb or a spaz (or none)
        except Exception: nodeDelegate = None
        if node is not None and node.exists():
            if isinstance(nodeDelegate, PlayerSpaz_Grab):
                if nodeDelegate.getPlayer() is self.sourcePlayer:
                    #print("Hit by own self, don't blow")
                    return True
            if (node is self.owner) or ((isinstance(nodeDelegate,bs.Bomb) or isinstance(nodeDelegate, Egg) or isinstance(nodeDelegate,bs.SpazBot)) and nodeDelegate.sourcePlayer is self.sourcePlayer): 
                #print("Hit by owr own bomb")
                return
            else: 
                #print 'exploded handling impact'
                self.handleMessage(bsBomb.ExplodeMessage())            

class Egg(bs.Actor):

    def __init__(self, position=(0,1,0), sourcePlayer=None, owner=None):
        bs.Actor.__init__(self)

        activity = self.getActivity()
        
        # spawn just above the provided point
        self._spawnPos = (position[0], position[1]+1.0, position[2])
        #This line was replaced by 'color' belwo: 'colorTexture': bsBomb.BombFactory().impactTex,
        self.node = bs.newNode("prop",
                               attrs={'model': activity._ballModel,
                                      'body':'sphere',
                                      'colorTexture': bs.getTexture("frostyColor"),
                                      'reflection':'soft',
                                      'modelScale':2.0,
                                      'bodyScale':2.0,
                                      'density':0.08,
                                      'reflectionScale':[0.15],
                                      'shadowSize': 0.6,
                                      'position':self._spawnPos,
                                      'materials': [bs.getSharedObject('objectMaterial'),activity._bombMat]
                                      },
                               delegate=self)
        self.sourcePlayer = sourcePlayer
        self.owner = owner
    def handleMessage(self,m):
        if isinstance(m,bs.DieMessage):
            self.node.delete()
        elif isinstance(m,bs.DroppedMessage): self._handleDropped(m)
        elif isinstance(m,bs.OutOfBoundsMessage):
            self.handleMessage(bs.DieMessage())
        elif isinstance(m,bs.HitMessage):
            self.node.handleMessage("impulse",m.pos[0],m.pos[1],m.pos[2],
                                    m.velocity[0],m.velocity[1],m.velocity[2],
                                    1.0*m.magnitude,1.0*m.velocityMagnitude,m.radius,0,
                                    m.forceDirection[0],m.forceDirection[1],m.forceDirection[2])
        else:
            bs.Actor.handleMessage(self,m)
    def _handleDropped(self,m):
        if self.exists():
            bs.gameTimer(int(self.getActivity().settings['Egg Lifetime']*1000),self._disappear)
    def _disappear(self):
        if self.node.exists():
            scl = self.node.modelScale
            bsUtils.animate(self.node,"modelScale",{0:scl*1.0, 300:scl*0.5, 500:0.0})
            self.maxSpeed = 0
            if self.hatch and self.sourcePlayer.exists():
                if len(self.sourcePlayer.gameData['bots']) < 3:
                    self.materials = []
                    p = self.node.position
                    #self.getActivity()._bots.spawnBot(ToughGuyFrostBot,pos=(p[0],p[1]-0.8,p[2]),spawnTime=0, onSpawnCall=self.setupFrosty)
                    self.sourcePlayer.gameData['bset'].spawnBot(ToughGuyFrostBot,pos=(p[0],p[1]-0.8,p[2]),spawnTime=0, onSpawnCall=self.setupFrosty)
            bs.gameTimer(550,bs.WeakCall(self.handleMessage,bs.DieMessage()))
    def setupFrosty(self,spaz):
        spaz.sourcePlayer = self.sourcePlayer
        spaz.sourcePlayer.gameData['bots'].append(spaz)
        bs.gameTimer(5000,bs.WeakCall(spaz.handleMessage,bs.DieMessage())) #Kill spaz after 5 seconds
        #bsUtils.animate(spaz.node, "modelScale",{0:0.1, 500:0.3, 800:1.2, 1000:1.0})

class zBotSet(bs.BotSet):   #the botset is overloaded to prevent adding players to the bots' targets if they are zombies too.         
    def startMoving(self): #here we overload the default startMoving, which normally calls _update.
        #self._botUpdateTimer = bs.Timer(50,bs.WeakCall(self._update),repeat=True)
        self._botUpdateTimer = bs.Timer(50,bs.WeakCall(self.zUpdate),repeat=True)
        
    def zUpdate(self):

        # update one of our bot lists each time through..
        # first off, remove dead bots from the list
        # (we check exists() here instead of dead.. we want to keep them around even if they're just a corpse)
        #####This is overloaded from bsSpaz to walk over other players' mines, but not source player.
        try:
            botList = self._botLists[self._botUpdateList] = [b for b in self._botLists[self._botUpdateList] if b.exists()]
        except Exception:
            bs.printException("error updating bot list: "+str(self._botLists[self._botUpdateList]))
        self._botUpdateList = (self._botUpdateList+1)%self._botListCount

        # update our list of player points for the bots to use
        playerPts = []
        for player in bs.getActivity().players:
            try:
                if player.exists():
                    if not player is self.sourcePlayer:  #If the player has lives, add to attack points
                        for m in player.gameData['mines']:
                            if not m.isHome and m.exists():
                                playerPts.append((bs.Vector(*m.node.position),
                                        bs.Vector(0,0,0)))
            except Exception:
                bs.printException('error on bot-set _update')

        for b in botList:
            b._setPlayerPts(playerPts)
            b._updateAI()
        
class ToughGuyFrostBot(bsSpaz.SpazBot):
    """
    category: Bot Classes
    
    A manly bot who walks and punches things.
    """
    character = 'Frosty'
    color = (1,1,1)
    highlight = (1,1,1)
    punchiness = 0.0
    chargeDistMax = 9999.0
    chargeSpeedMin = 1.0
    chargeSpeedMax = 1.0
    throwDistMin = 9999
    throwDistMax = 9999
    
    def handleMessage(self,m):
        if isinstance(m, bs.PickedUpMessage):
            self.handleMessage(bs.DieMessage())
        super(self.__class__, self).handleMessage(m)

    
class LandGrab(bs.TeamGameActivity):

    @classmethod
    def getName(cls):
        return 'Land Grab'

    @classmethod
    def getScoreInfo(cls):
        return {'scoreName':'score',
                'scoreType':'points',
                'noneIsWinner':False,
                'lowerIsBetter':False}
                
    @classmethod
    def supportsSessionType(cls, sessionType):
        return True if issubclass(sessionType,bs.FreeForAllSession) else False
    
    @classmethod
    def getDescription(cls,sessionType):
        return 'Grow your territory'

    @classmethod
    def getSupportedMaps(cls,sessionType):
        return ['Doom Shroom', 'Rampage', 'Hockey Stadium', 'Crag Castle', 'Big G', 'Football Stadium']

    @classmethod
    def getSettings(cls,sessionType):
        return [("Claim Size",{'minValue':2,'default':5,'increment':1}),
                ("Min Sec btw Claims",{'minValue':1,'default':3,'increment':1}),
                ("Eggs Not Bombs",{'default':True}),
                ("Snowman Eggs",{'default':True}),
                ("Egg Lifetime",{'minValue':0.5,'default':2.0,'increment':0.5}),
                ("Time Limit",{'choices':[('30 Seconds',30),('1 Minute',60),
                                            ('90 Seconds',90),('2 Minutes',120),
                                            ('3 Minutes',180),('5 Minutes',300)],'default':60}),
                ("Respawn Times",{'choices':[('Shorter',0.25),('Short',0.5),('Normal',1.0),('Long',2.0),('Longer',4.0)],'default':1.0}),
                ("Epic Mode",{'default':False})]

    def __init__(self,settings):
        bs.TeamGameActivity.__init__(self, settings)

        if self.settings['Epic Mode']: self._isSlowMotion = True        
        # print messages when players die (since its meaningful in this game)
        self.announcePlayerDeaths = True
        self._scoreBoard = bs.ScoreBoard()
        #self._lastPlayerDeathTime = None    

        self.minOverlap = 0.2 # This is the minimum amount of linear overlap for a spaz's own area to guarantee they can walk to it
        self.claimRad = math.sqrt(self.settings['Claim Size']/3.1416) #This is so that the settings can be in units of area, same as score
        self.updateRate = 200 #update the mine radii etc every this many milliseconds
        #This game's score calculation is very processor intensive.
        #Score only updated 2x per second during game, at lower resolution
        self.scoreUpdateRate = 1000
        self.inGameScoreRes = 40
        self.finalScoreRes = 300
        self._eggModel = bs.getModel('egg')
        try: myFactory = self._sharedSpazFactory
        except Exception:
            myFactory = self._sharedSpazFactory = bsSpaz.SpazFactory()
        m=myFactory._getMedia('Frosty')
        self._ballModel = m['pelvisModel']
        self._bombMat = bsBomb.BombFactory().bombMaterial
        self._mineIconTex=bs.Powerup.getFactory().texLandMines

    def getInstanceDescription(self):
        return ('Control territory with mines')

    def getInstanceScoreBoardDescription(self):
        return ('Control the most territory with mines\nDouble punch to switch between mines and bombs\n')

    def onTransitionIn(self):
        bs.TeamGameActivity.onTransitionIn(self, music='Epic' if self.settings['Epic Mode'] else 'Survival')
        self._startGameTime = bs.getGameTime()
        
    def onBegin(self):
        bs.TeamGameActivity.onBegin(self)
        self.setupStandardTimeLimit(self.settings['Time Limit'])
        bs.gameTimer(self.scoreUpdateRate, bs.WeakCall(self._updateScoreBoard), repeat=True)
        bs.gameTimer(1000, bs.WeakCall(self.startUpdating), repeat=False)#Delay to allow for home mine to spawn
        #self._bots = bs.BotSet() 
        # check for immediate end (if we've only got 1 player, etc)
        #bs.gameTimer(5000, self._checkEndGame)

    def onTeamJoin(self,team):
        team.gameData['spawnOrder'] = []
        team.gameData['score'] = 0        
        
    def onPlayerJoin(self, player):
        # don't allow joining after we start
        # (would enable leave/rejoin tomfoolery)
        player.gameData['mines'] = []
        if self.hasBegun():
            bs.screenMessage(bs.Lstr(resource='playerDelayedJoinText',subs=[('${PLAYER}',player.getName(full=True))]),color=(0,1,0))
            # for score purposes, mark them as having died right as the game started
            #player.gameData['deathTime'] = self._timer.getStartTime()
            return
        player.gameData['home'] = None
        player.gameData['bots'] = []
        player.gameData['bset'] = zBotSet()
        player.gameData['bset'].sourcePlayer = player
        self.spawnPlayer(player)
        
    def onPlayerLeave(self, player):
         # augment default behavior...
        for m in player.gameData['mines']:
            m.handleMessage(bs.DieMessage())
        player.gameData['mines'] = []
        bs.TeamGameActivity.onPlayerLeave(self, player)
        # a departing player may trigger game-over
        self._checkEndGame()

    def startUpdating(self):
        bs.gameTimer(self.updateRate, bs.WeakCall(self.mineUpdate), repeat=True)

    def _updateScoreBoard(self):
        for team in self.teams:
            team.gameData['score'] = self.areaCalc(team,self.inGameScoreRes)
            self._scoreBoard.setTeamValue(team,team.gameData['score'])
        
    def mineUpdate(self):
        for player in self.players:
            #Need to purge mines, whether or not player is living
            for m in player.gameData['mines']:
                if not m.exists():
                    player.gameData['mines'].remove(m)
            if not player.actor is None:
                if player.actor.isAlive():
                    pSafe = False
                    p1 = player.actor.node.position
                    for teamP in player.getTeam().players:
                        for m in teamP.gameData['mines']:
                            if m.exists():
                                if not m._exploded:
                                    p2 = m.node.position
                                    diff = (bs.Vector(p1[0]-p2[0],0.0,p1[2]-p2[2]))
                                    dist = (diff.length())
                                    if dist < m.rad:
                                        pSafe = True
                                        break
                    if not pSafe:
                        #print player.getName(), "died with mines:", len(player.gameData['mines'])
                        player.actor.handleMessage(bs.DieMessage())
        

    def endGame(self):
        results = bs.TeamGameResults()
        for t in self.teams: results.setTeamScore(t,t.gameData['score'])
        self.end(results=results,announceDelay=800)
        
    def _flashPlayer(self,player,scale):
        pos = player.actor.node.position
        light = bs.newNode('light',
                           attrs={'position':pos,
                                  'color':(1,1,0),
                                  'heightAttenuated':False,
                                  'radius':0.4})
        bs.gameTimer(500,light.delete)
        bs.animate(light,'intensity',{0:0,100:1.0*scale,500:0})


    def handleMessage(self,m):

        if isinstance(m, bs.SpazBotDeathMessage):
            if m.badGuy.sourcePlayer.exists():
                m.badGuy.sourcePlayer.gameData['bots'].remove(m.badGuy)
        elif isinstance(m,bs.PlayerSpazDeathMessage):

            bs.TeamGameActivity.handleMessage(self,m) # (augment standard behavior)
            self.respawnPlayer(m.spaz.getPlayer())
            #deathTime = bs.getGameTime()
            
            # record the player's moment of death
            #m.spaz.getPlayer().gameData['deathTime'] = deathTime

            # in co-op mode, end the game the instant everyone dies (more accurate looking)
            # in teams/ffa, allow a one-second fudge-factor so we can get more draws
            #if isinstance(self.getSession(),bs.CoopSession):
                # teams will still show up if we check now.. check in the next cycle
            #    bs.pushCall(self._checkEndGame)
            #    self._lastPlayerDeathTime = deathTime # also record this for a final setting of the clock..
            #else:
                #bs.gameTimer(1000, self._checkEndGame)

        else:
            # default handler:
            bs.TeamGameActivity.handleMessage(self,m)

    def _checkEndGame(self):
        livingTeamCount = 0
        for team in self.teams:
            for player in team.players:
                if player.isAlive():
                    livingTeamCount += 1
                    break

        # in co-op, we go till everyone is dead.. otherwise we go until one team remains
        if isinstance(self.getSession(),bs.CoopSession):
            if livingTeamCount <= 0: self.endGame()
        else:
            if livingTeamCount <= 1: self.endGame()

    def spawnPlayer(self, player):
        #Overloaded for this game to respawn at home instead of random FFA spots
        if not player.exists():
            bs.printError('spawnPlayer() called for nonexistant player')
            return
        if player.gameData['home'] is None:
            pos = self.getMap().getFFAStartPosition(self.players)
            bomb = myMine(pos,
                           (0.0,0.0,0.0),
                           0.0,
                           player,
                           None).autoRetain()
            bomb.isHome = True
            bomb.handleMessage(bsBomb.ArmMessage())
            position = [pos[0],pos[1]+0.3,pos[2]]
            player.gameData['home'] = position
            player.gameData['mines'].append(bomb)
        else:
            position = player.gameData['home']
        spaz = self.spawnPlayerSpaz(player, position)

        # lets reconnect this player's controls to this
        # spaz but *without* the ability to attack or pick stuff up
        spaz.connectControlsToPlayer(enablePunch=True,
                                     enableBomb=True,
                                     enablePickUp=True)
        #Wire up the spaz with mines
        spaz.landMineCount = 1
        spaz.node.billboardTexture = self._mineIconTex
        bs.animate(spaz.node,"billboardOpacity",{0:0.0,100:1.0,400:1.0})
        t = bs.getGameTime()
        if t - spaz.lastMine < spaz.mineTimeout:
            spaz.node.billboardCrossOut = True
            bs.gameTimer((spaz.mineTimeout-t+spaz.lastMine),bs.WeakCall(spaz.unCrossBillboard))
        spaz.dropEggs = self.settings['Eggs Not Bombs']
        spaz.eggsHatch = self.settings['Snowman Eggs']

        # also lets have them make some noise when they die..
        spaz.playBigDeathSound = True  
      
    def spawnPlayerSpaz(self,player,position=(0,0,0),angle=None):
        """
        Create and wire up a bs.PlayerSpaz for the provide bs.Player.
        """
        #position = self.getMap().getFFAStartPosition(self.players)
        name = player.getName()
        color = player.color
        highlight = player.highlight

        lightColor = bsUtils.getNormalizedColor(color)
        displayColor = bs.getSafeColor(color,targetIntensity=0.75)
        spaz = PlayerSpaz_Grab(color=color,
                             highlight=highlight,
                             character=player.character,
                             player=player)
        player.setActor(spaz)

        # we want a bigger area-of-interest in co-op mode
        # if isinstance(self.getSession(),bs.CoopSession): spaz.node.areaOfInterestRadius = 5.0
        # else: spaz.node.areaOfInterestRadius = 5.0

        # if this is co-op and we're on Courtyard or Runaround, add the material that allows us to
        # collide with the player-walls
        # FIXME; need to generalize this
        if isinstance(self.getSession(),bs.CoopSession) and self.getMap().getName() in ['Courtyard','Tower D']:
            mat = self.getMap().preloadData['collideWithWallMaterial']
            spaz.node.materials += (mat,)
            spaz.node.rollerMaterials += (mat,)
        
        spaz.node.name = name
        spaz.node.nameColor = displayColor
        spaz.connectControlsToPlayer()
        
        ###These special attributes are for Land Grab:
        spaz.lastMine = 0
        spaz.mineTimeout = self.settings['Min Sec btw Claims'] * 1000
        
        self.scoreSet.playerGotNewSpaz(player,spaz)

        # move to the stand position and add a flash of light
        spaz.handleMessage(bs.StandMessage(position,angle if angle is not None else random.uniform(0,360)))
        t = bs.getGameTime()
        bs.playSound(self._spawnSound,1,position=spaz.node.position)
        light = bs.newNode('light',attrs={'color':lightColor})
        spaz.node.connectAttr('position',light,'position')
        bsUtils.animate(light,'intensity',{0:0,250:1,500:0})
        bs.gameTimer(500,light.delete)
        return spaz
    def getRandomPowerupPoint(self):
        #So far, randomized points only figured out for mostly rectangular maps.
        #Boxes will still fall through holes, but shouldn't be terrible problem (hopefully)
        #If you add stuff here, need to add to "supported maps" above.
        #['Doom Shroom', 'Rampage', 'Hockey Stadium', 'Courtyard', 'Crag Castle', 'Big G', 'Football Stadium']
        myMap = self.getMap().getName()
        #print(myMap)
        if myMap == 'Doom Shroom':
            while True:
                x = random.uniform(-1.0,1.0)
                y = random.uniform(-1.0,1.0)
                if x*x+y*y < 1.0: break
            return ((8.0*x,2.5,-3.5+5.0*y))
        elif myMap == 'Rampage':
            x = random.uniform(-6.0,7.0)
            y = random.uniform(-6.0,-2.5)
            return ((x, 5.2, y))
        elif myMap == 'Hockey Stadium':
            x = random.uniform(-11.5,11.5)
            y = random.uniform(-4.5,4.5)
            return ((x, 0.2, y))
        elif myMap == 'Courtyard':
            x = random.uniform(-4.3,4.3)
            y = random.uniform(-4.4,0.3)
            return ((x, 3.0, y))
        elif myMap == 'Crag Castle':
            x = random.uniform(-6.7,8.0)
            y = random.uniform(-6.0,0.0)
            return ((x, 10.0, y))
        elif myMap == 'Big G':
            x = random.uniform(-8.7,8.0)
            y = random.uniform(-7.5,6.5)
            return ((x, 3.5, y))
        elif myMap == 'Football Stadium':
            x = random.uniform(-12.5,12.5)
            y = random.uniform(-5.0,5.5)
            return ((x, 0.32, y))
        else:
            x = random.uniform(-5.0,5.0)
            y = random.uniform(-6.0,0.0)
            return ((x, 8.0, y))

    def areaCalc(self,team,res):
        ##This routine calculates (well, approximates) the area covered by a team
        ##and returns their score.  the "res" argument is the resolution.  Higher res,
        ##better approximation.
        ##Most of this code was stolen from rosettacode.org/wiki/Total_circles_area
        circles = ()
        for p in team.players:
            for m in p.gameData['mines']:
                if m.exists():
                    if m.rad != 0:
                        if not m._exploded:
                            circles += ((m.node.position[0],m.node.position[2], m.rad),)
        # compute the bounding box of the circles
        if len(circles) == 0: return 0
        x_min = min(c[0] - c[2] for c in circles)
        x_max = max(c[0] + c[2] for c in circles)
        y_min = min(c[1] - c[2] for c in circles)
        y_max = max(c[1] + c[2] for c in circles)
     
        box_side = res
     
        dx = (x_max - x_min) / box_side
        dy = (y_max - y_min) / box_side
     
        count = 0
     
        for r in xrange(box_side):
            y = y_min + r * dy
            for c in xrange(box_side):
                x = x_min + c * dx
                if any((x-circle[0])**2 + (y-circle[1])**2 <= (circle[2] ** 2)
                       for circle in circles):
                    count += 1
     
        return int(count * dx * dy  *10)    
            
    def endGame(self):

        if self.hasEnded(): return
        #sorryTxt = bsUtils.Text('Calculating final scores!...')
        for team in self.teams:
            team.gameData['score'] = str(round(self.areaCalc(team,self.finalScoreRes),2))
        #sorryTxt.handleMessage(bs.DieMessage())
        #print 'calc time:', (bs.getRealTime() - t)
        bs.gameTimer(300, bs.Call(self.waitForScores))
    def waitForScores(self):
        results = bs.TeamGameResults()
        self._vsText = None # kill our 'vs' if its there
        for team in self.teams:
            results.setTeamScore(team, team.gameData['score'])
        self.end(results=results)


import bsSpaz
import bs
import bsUtils
import weakref
import random

class BunnyBuddyBot(bsSpaz.SpazBot):
    """
    category: Bot Classes
    
    A speedy attacking melee bot.
    """

    color=(1,1,1)
    highlight=(1.0,0.5,0.5)
    character = 'Easter Bunny'
    punchiness = 1.0
    run = True
    bouncy = True
    defaultBoxingGloves = True
    chargeDistMin = 1.0
    chargeDistMax = 9999.0
    chargeSpeedMin = 1.0
    chargeSpeedMax = 1.0
    throwDistMin = 3
    throwDistMax = 6
    pointsMult = 2
    
    def __init__(self,player):
        """
        Instantiate a spaz-bot.
        """
        self.color = player.color
        self.highlight = player.highlight
        bsSpaz.Spaz.__init__(self,color=self.color,highlight=self.highlight,character=self.character,
                      sourcePlayer=None,startInvincible=False,canAcceptPowerups=False)

        # if you need to add custom behavior to a bot, set this to a callable which takes one
        # arg (the bot) and returns False if the bot's normal update should be run and True if not
        self.updateCallback = None
        self._map = weakref.ref(bs.getActivity().getMap())

        self.lastPlayerAttackedBy = None # FIXME - should use empty player-refs
        self.lastAttackedTime = 0
        self.lastAttackedType = None
        self.targetPointDefault = None
        self.heldCount = 0
        self.lastPlayerHeldBy = None # FIXME - should use empty player-refs here
        self.targetFlag = None
        self._chargeSpeed = 0.5*(self.chargeSpeedMin+self.chargeSpeedMax)
        self._leadAmount = 0.5
        self._mode = 'wait'
        self._chargeClosingIn = False
        self._lastChargeDist = 0.0
        self._running = False
        self._lastJumpTime = 0    
        
class BunnyBotSet(bsSpaz.BotSet):
    """
    category: Bot Classes
    
    A container/controller for one or more bs.SpazBots.
    """
    def __init__(self, sourcePlayer):
        """
        Create a bot-set.
        """
        # we spread our bots out over a few lists so we can update them in a staggered fashion
        self._botListCount = 5
        self._botAddList = 0
        self._botUpdateList = 0
        self._botLists = [[] for i in range(self._botListCount)]
        self._spawnSound = bs.getSound('spawn')
        self._spawningCount = 0
        self.startMovingBunnies()
        self.sourcePlayer = sourcePlayer
        

    def doBunny(self):
        self.spawnBot(BunnyBuddyBot, self.sourcePlayer.actor.node.position, 2000, self.setupBunny)
        
    def startMovingBunnies(self):
        self._botUpdateTimer = bs.Timer(50,bs.WeakCall(self._bUpdate),repeat=True)
        
    def _spawnBot(self,botType,pos,onSpawnCall):
        spaz = botType(self.sourcePlayer)
        bs.playSound(self._spawnSound,position=pos)
        spaz.node.handleMessage("flash")
        spaz.node.isAreaOfInterest = 0
        spaz.handleMessage(bs.StandMessage(pos,random.uniform(0,360)))
        self.addBot(spaz)
        self._spawningCount -= 1
        if onSpawnCall is not None: onSpawnCall(spaz)
        
    def _bUpdate(self):

        # update one of our bot lists each time through..
        # first off, remove dead bots from the list
        # (we check exists() here instead of dead.. we want to keep them around even if they're just a corpse)

        try:
            botList = self._botLists[self._botUpdateList] = [b for b in self._botLists[self._botUpdateList] if b.exists()]
        except Exception:
            bs.printException("error updating bot list: "+str(self._botLists[self._botUpdateList]))
        self._botUpdateList = (self._botUpdateList+1)%self._botListCount

        # update our list of player points for the bots to use
        playerPts = []

        try:
            #if player.isAlive() and not (player is self.sourcePlayer):
            #    playerPts.append((bs.Vector(*player.actor.node.position),
            #                     bs.Vector(*player.actor.node.velocity)))
            for n in bs.getNodes():
                if n.getNodeType() == 'spaz':
                    s = n.getDelegate()
                    if isinstance(s,bsSpaz.SpazBot):
                        if not s in self.getLivingBots():
                            if hasattr(s, 'sourcePlayer'):
                                if not s.sourcePlayer is self.sourcePlayer:
                                    playerPts.append((bs.Vector(*n.position), bs.Vector(*n.velocity)))
                            else:
                                playerPts.append((bs.Vector(*n.position), bs.Vector(*n.velocity)))
                    elif isinstance(s, bsSpaz.PlayerSpaz):
                        if not (s.getPlayer() is self.sourcePlayer):
                            playerPts.append((bs.Vector(*n.position), bs.Vector(*n.velocity)))
        except Exception:
            bs.printException('error on bot-set _update')

        for b in botList:
            b._setPlayerPts(playerPts)
            b._updateAI()
    def setupBunny(self, spaz):
        spaz.sourcePlayer = self.sourcePlayer
        spaz.color = self.sourcePlayer.color
        spaz.highlight = self.sourcePlayer.highlight
        self.setBunnyText(spaz)
    def setBunnyText(self, spaz):
        m = bs.newNode('math', owner=spaz.node, attrs={'input1': (0, 0.7, 0), 'operation': 'add'})
        spaz.node.connectAttr('position', m, 'input2')
        spaz._bunnyText = bs.newNode('text',
                                      owner=spaz.node,
                                      attrs={'text':self.sourcePlayer.getName(),
                                             'inWorld':True,
                                             'shadow':1.0,
                                             'flatness':1.0,
                                             'color':self.sourcePlayer.color,
                                             'scale':0.0,
                                             'hAlign':'center'})
        m.connectAttr('output', spaz._bunnyText, 'position')
        bs.animate(spaz._bunnyText, 'scale', {0: 0.0, 1000: 0.01})
        
        import bs
import weakref

def bsGetAPIVersion():
    # see bombsquadgame.com/apichanges
    return 4

def bsGetGames():
    return [BoxingOfTheHillGame]

class BoxingOfTheHillGame(bs.TeamGameActivity):

    FLAG_NEW = 0
    FLAG_UNCONTESTED = 1
    FLAG_CONTESTED = 2
    FLAG_HELD = 3

    @classmethod
    def getName(cls):
        return 'Boxing of the Hill'

    @classmethod
    def getDescription(cls,sessionType):
        return 'Secure the flag for a set length of time. Gloves only!'

    @classmethod
    def getScoreInfo(cls):
        return {'scoreName':'Time Held'}
    
    @classmethod
    def supportsSessionType(cls,sessionType):
        return True if (issubclass(sessionType,bs.TeamsSession)
                        or issubclass(sessionType,bs.FreeForAllSession)) else False

    @classmethod
    def getSupportedMaps(cls,sessionType):
        return bs.getMapsSupportingPlayType("kingOfTheHill")

    @classmethod
    def getSettings(cls,sessionType):
        return [("Hold Time",{'minValue':10,'default':30,'increment':10}),
                ("Time Limit",{'choices':[('None',0),('1 Minute',60),
                                        ('2 Minutes',120),('5 Minutes',300),
                                        ('10 Minutes',600),('20 Minutes',1200)],'default':0}),
                ("Respawn Times",{'choices':[('Shorter',0.25),('Short',0.5),('Normal',1.0),('Long',2.0),('Longer',4.0)],'default':1.0})]

    def __init__(self,settings):
        bs.TeamGameActivity.__init__(self,settings)
        self._scoreBoard = bs.ScoreBoard()
        self._swipSound = bs.getSound("swip")
        self._tickSound = bs.getSound('tick')
        self._countDownSounds = {10:bs.getSound('announceTen'),
                                 9:bs.getSound('announceNine'),
                                 8:bs.getSound('announceEight'),
                                 7:bs.getSound('announceSeven'),
                                 6:bs.getSound('announceSix'),
                                 5:bs.getSound('announceFive'),
                                 4:bs.getSound('announceFour'),
                                 3:bs.getSound('announceThree'),
                                 2:bs.getSound('announceTwo'),
                                 1:bs.getSound('announceOne')}

        self._flagRegionMaterial = bs.Material()
        self._flagRegionMaterial.addActions(conditions=("theyHaveMaterial",bs.getSharedObject('playerMaterial')),
                                            actions=(("modifyPartCollision","collide",True),
                                                     ("modifyPartCollision","physical",False),
                                                     ("call","atConnect",bs.Call(self._handlePlayerFlagRegionCollide,1)),
                                                     ("call","atDisconnect",bs.Call(self._handlePlayerFlagRegionCollide,0))))

    def getInstanceDescription(self):
        return ('Secure the flag for ${ARG1} seconds.',self.settings['Hold Time'])

    def getInstanceScoreBoardDescription(self):
        return ('secure the flag for ${ARG1} seconds',self.settings['Hold Time'])

    def onTransitionIn(self):
        bs.TeamGameActivity.onTransitionIn(self, music='Scary')

    def onTeamJoin(self,team):
        team.gameData['timeRemaining'] = self.settings["Hold Time"]
        self._updateScoreBoard()

    def onPlayerJoin(self,player):
        bs.TeamGameActivity.onPlayerJoin(self,player)
        player.gameData['atFlag'] = 0

    def onBegin(self):
        bs.TeamGameActivity.onBegin(self)
        self.setupStandardTimeLimit(self.settings['Time Limit'])
        # self.setupStandardPowerupDrops() #no powerups due to boxing
        self._flagPos = self.getMap().getFlagPosition(None)
        bs.gameTimer(1000,self._tick,repeat=True)
        self._flagState = self.FLAG_NEW
        self.projectFlagStand(self._flagPos)

        self._flag = bs.Flag(position=self._flagPos,
                             touchable=False,
                             color=(1,1,1))
        self._flagLight = bs.newNode('light',
                                     attrs={'position':self._flagPos,
                                            'intensity':0.2,
                                            'heightAttenuated':False,
                                            'radius':0.4,
                                            'color':(0.2,0.2,0.2)})

        # flag region
        bs.newNode('region',
                   attrs={'position':self._flagPos,
                          'scale': (1.8,1.8,1.8),
                          'type': 'sphere',
                          'materials':[self._flagRegionMaterial,bs.getSharedObject('regionMaterial')]})
        self._updateFlagState()

    def spawnPlayer(self,player):

        spaz = self.spawnPlayerSpaz(player)
        spaz.connectControlsToPlayer(enablePunch=True,
                                     enableBomb=False,
                                     enablePickUp=True)

        spaz.equipBoxingGloves()

    

    def _tick(self):
        self._updateFlagState()

        # give holding players points
        for player in self.players:
            if player.gameData['atFlag'] > 0:
                self.scoreSet.playerScored(player,3,screenMessage=False,display=False)

        scoringTeam = None if self._scoringTeam is None else self._scoringTeam()
        if scoringTeam:

            if scoringTeam.gameData['timeRemaining'] > 0: bs.playSound(self._tickSound)

            scoringTeam.gameData['timeRemaining'] = max(0,scoringTeam.gameData['timeRemaining']-1)
            self._updateScoreBoard()
            if scoringTeam.gameData['timeRemaining'] > 0:
                self._flag.setScoreText(str(scoringTeam.gameData['timeRemaining']))

            # announce numbers we have sounds for
            try: bs.playSound(self._countDownSounds[scoringTeam.gameData['timeRemaining']])
            except Exception: pass

            # winner
            if scoringTeam.gameData['timeRemaining'] <= 0:
                self.endGame()

    def endGame(self):
        results = bs.TeamGameResults()
        for team in self.teams: results.setTeamScore(team,self.settings['Hold Time'] - team.gameData['timeRemaining'])
        self.end(results=results,announceDelay=0)
        
    def _updateFlagState(self):
        holdingTeams = set(player.getTeam() for player in self.players if player.gameData['atFlag'])
        prevState = self._flagState
        if len(holdingTeams) > 1:
            self._flagState = self.FLAG_CONTESTED
            self._scoringTeam = None
            self._flagLight.color = (0.6,0.6,0.1)
            self._flag.node.color = (1.0,1.0,0.4)
        elif len(holdingTeams) == 1:
            holdingTeam = list(holdingTeams)[0]
            self._flagState = self.FLAG_HELD
            self._scoringTeam = weakref.ref(holdingTeam)
            self._flagLight.color = bs.getNormalizedColor(holdingTeam.color)
            self._flag.node.color = holdingTeam.color
        else:
            self._flagState = self.FLAG_UNCONTESTED
            self._scoringTeam = None
            self._flagLight.color = (0.2,0.2,0.2)
            self._flag.node.color = (1,1,1)
        if self._flagState != prevState:
            bs.playSound(self._swipSound)

    def _handlePlayerFlagRegionCollide(self,colliding):
        flagNode,playerNode = bs.getCollisionInfo("sourceNode","opposingNode")
        try: player = playerNode.getDelegate().getPlayer()
        except Exception: return

        # different parts of us can collide so a single value isn't enough
        # also don't count it if we're dead (flying heads shouldnt be able to win the game :-)
        if colliding and player.isAlive(): player.gameData['atFlag'] += 1
        else: player.gameData['atFlag'] = max(0,player.gameData['atFlag'] - 1)

        self._updateFlagState()

    def _updateScoreBoard(self):
        for team in self.teams:
            self._scoreBoard.setTeamValue(team,team.gameData['timeRemaining'],self.settings['Hold Time'],countdown=True)

    def handleMessage(self,m):
        if isinstance(m,bs.PlayerSpazDeathMessage):
            bs.TeamGameActivity.handleMessage(self,m) # augment default
            
            # no longer can count as atFlag once dead
            player = m.spaz.getPlayer()
            player.gameData['atFlag'] = 0
            self._updateFlagState()
            self.respawnPlayer(player)
            
            from __future__ import print_function
import bs
import bsInternal
import os
import urllib
import urllib2
import httplib
import json
import random
import time
import threading
import weakref
from md5 import md5
from bsUI import gSmallUI, gMedUI, gHeadingColor, uiGlobals, ConfirmWindow, StoreWindow, MainMenuWindow, Window
from functools import partial

try:
    from settings_patcher import SettingsButton
except ImportError:
    bs.screenMessage("library settings_patcher missing", color=(1, 0, 0))
    raise
try:
    from ui_wrappers import TextWidget, ContainerWidget, ButtonWidget, CheckBoxWidget, ScrollWidget, ColumnWidget, Widget
except ImportError:
    bs.screenMessage("library ui_wrappers missing", color=(1, 0, 0))
    raise


# roll own uuid4 implementation because uuid module might not be available
# this is broken on android/1.4.216 due to 16**8 == 0 o.O
def uuid4():
    components = [8, 4, 4, 4, 12]
    return "-".join([('%012x' % random.randrange(16**a))[12 - a:] for a in components])

PROTOCOL_VERSION = 1.1
STAT_SERVER_URI = None # "http://bsmm.thuermchen.com"
SUPPORTS_HTTPS = hasattr(httplib, 'HTTPS')
USER_REPO = "Mrmaxmeier/BombSquad-Community-Mod-Manager"

_supports_auto_reloading = True
_auto_reloader_type = "patching"
StoreWindow_setTab = StoreWindow._setTab
MainMenuWindow__init__ = MainMenuWindow.__init__


def _prepare_reload():
    settingsButton.remove()
    MainMenuWindow.__init__ = MainMenuWindow__init__
    del MainMenuWindow._cb_checkUpdateData
    StoreWindow._setTab = StoreWindow_setTab
    del StoreWindow._onGetMoreGamesPress


def bsGetAPIVersion():
    return 4

quittoapply = None
checkedMainMenu = False


if 'mod_manager_config' not in bs.getConfig():
    bs.getConfig()['mod_manager_config'] = {}
    bs.writeConfig()

config = bs.getConfig()['mod_manager_config']


def index_url(branch=None):
    if not branch:
        branch = config.get("branch", "master")
    if SUPPORTS_HTTPS:
        yield "https://raw.githubusercontent.com/{}/{}/index.json".format(USER_REPO, branch)
        yield "https://rawgit.com/{}/{}/index.json".format(USER_REPO, branch)
    yield "http://raw.githack.com/{}/{}/index.json".format(USER_REPO, branch)
    yield "http://rawgit.com/{}/{}/index.json".format(USER_REPO, branch)


def mod_url(data):
    if "commit_sha" in data and "filename" in data:
        commit_hexsha = data["commit_sha"]
        filename = data["filename"]
        if SUPPORTS_HTTPS:
            yield "https://cdn.rawgit.com/{}/{}/mods/{}".format(USER_REPO, commit_hexsha, filename)
        yield "http://rawcdn.githack.com/{}/{}/mods/{}".format(USER_REPO, commit_hexsha, filename)
    if "url" in data:
        if SUPPORTS_HTTPS:
            yield data["url"]
        yield data["url"].replace("https", "http")


def try_fetch_cb(generator, callback, **kwargs):
    def f(data, status_code):
        if data:
            callback(data, status_code)
        else:
            try:
                get_cached(next(generator), f, **kwargs)
            except StopIteration:
                callback(None, None)
    get_cached(next(generator), f, **kwargs)


web_cache = config.get("web_cache", {})
config["web_cache"] = web_cache

if STAT_SERVER_URI and 'uuid' not in config:
    config['uuid'] = uuid4()
    bs.writeConfig()


def get_cached(url, callback, force_fresh=False, fallback_to_outdated=True):
    def cache(data, status_code):
        if data:
            web_cache[url] = (data, time.time())
            bs.writeConfig()

    def f(data, status_code):
        # TODO: cancel prev fetchs
        callback(data, status_code)
        cache(data, status_code)

    if force_fresh:
        mm_serverGet(url, {}, f)
        return

    if url in web_cache:
        data, timestamp = web_cache[url]
        if timestamp + 10 * 30 > time.time():
            mm_serverGet(url, {}, cache)
        if fallback_to_outdated or timestamp + 10 * 60 > time.time():
            callback(data, None)
            return

    mm_serverGet(url, {}, f)


def get_index(callback, branch=None, **kwargs):
    try_fetch_cb(index_url(branch), callback, **kwargs)


def fetch_stats(callback, **kwargs):
    if STAT_SERVER_URI:
        url = STAT_SERVER_URI + "/stats?uuid=" + config['uuid']
        get_cached(url, callback, **kwargs)


def stats_cached():
    if not STAT_SERVER_URI:
        return False
    url = STAT_SERVER_URI + "/stats?uuid=" + config['uuid']
    return url in web_cache


def submit_mod_rating(mod, rating, callback):
    if not STAT_SERVER_URI:
        return bs.screenMessage('rating submission disabled')
    url = STAT_SERVER_URI + "/submit_rating"
    data = {
        "uuid": config['uuid'],
        "mod_str": mod.base,
        "rating": rating,
    }

    def cb(data, status_code):
        if status_code == 200:
            bs.screenMessage("rating submitted")
            callback()
        else:
            bs.screenMessage("failed to submit rating")

    mm_serverPost(url, data, cb, eval_data=False)


def submit_download(mod):
    if not config.get('submit-download-statistics', True) or not STAT_SERVER_URI:
        return

    url = STAT_SERVER_URI + "/submit_download"
    data = {
        "uuid": config.get('uuid'),
        "mod_str": mod.base,
    }

    def cb(data, status_code):
        if status_code != 200:
            print("failed to submit download stats")

    mm_serverPost(url, data, cb, eval_data=False)


def fetch_mod(data, callback):
    generator = mod_url(data)

    def f(data, status_code):
        if data:
            callback(data, status_code)
        else:
            try:
                mm_serverGet(next(generator), {}, f, eval_data=False)
            except StopIteration:
                callback(None, None)

    mm_serverGet(next(generator), {}, f, eval_data=False)


def process_server_data(data):
    mods = data["mods"]
    version = data["version"]
    if version - 0.5 > PROTOCOL_VERSION:
        print("version diff:", version, PROTOCOL_VERSION)
        bs.screenMessage("please manually update the mod manager")
    return mods, version


def _cb_checkUpdateData(self, data, status_code):
    try:
        if data:
            m, v = process_server_data(data)
            mods = [Mod(d) for d in m.values()]
            for mod in mods:
                mod._mods = {m.base: m for m in mods}
                if mod.is_installed() and mod.is_outdated():
                    if config.get("auto-update-old-mods", True):
                        bs.screenMessage("updating mod '{}'...".format(mod.name))

                        def cb(mod, success):
                            if success:
                                bs.screenMessage("updated mod '{}'.".format(mod.name))

                        mod.install(cb)
                    else:
                        bs.screenMessage("an update for mod '{}' is available!".format(mod.name))
    except:
        bs.printException()
        bs.screenMessage("failed to check for mod updates")


oldMainInit = MainMenuWindow.__init__


def newMainInit(self, transition='inRight'):
    global checkedMainMenu
    oldMainInit(self, transition)
    if checkedMainMenu:
        return
    checkedMainMenu = True
    if config.get("auto-check-updates", True):
        get_index(self._cb_checkUpdateData, force_fresh=True)

MainMenuWindow.__init__ = newMainInit
MainMenuWindow._cb_checkUpdateData = _cb_checkUpdateData


def _doModManager(swinstance):
    swinstance._saveState()
    bs.containerWidget(edit=swinstance._rootWidget, transition='outLeft')
    mm_window = ModManagerWindow(backLocationCls=swinstance.__class__)
    uiGlobals['mainMenuWindow'] = mm_window.getRootWidget()

settingsButton = SettingsButton(id="ModManager", icon="heart", sorting_position=6) \
    .setCallback(_doModManager) \
    .setText("Mod Manager") \
    .add()


class ModManager_ServerCallThread(threading.Thread):

    def __init__(self, request, requestType, data, callback, eval_data=True):
        threading.Thread.__init__(self)
        self._request = request.encode("ascii")  # embedded python2.7 has weird encoding issues
        self._requestType = requestType
        self._data = {} if data is None else data
        self._eval_data = eval_data
        self._callback = callback

        self._context = bs.Context('current')

        # save and restore the context we were created from
        activity = bs.getActivity(exceptionOnNone=False)
        self._activity = weakref.ref(activity) if activity is not None else None

    def _runCallback(self, *args):

        # if we were created in an activity context and that activity has since died, do nothing
        # (hmm should we be using a context-call instead of doing this manually?)
        if self._activity is not None and (self._activity() is None or self._activity().isFinalized()):
            return

        # (technically we could do the same check for session contexts, but not gonna worry about it for now)
        with self._context:
            self._callback(*args)

    def run(self):
        try:
            bsInternal._setThreadName("ModManager_ServerCallThread")  # FIXME: using protected apis
            env = {'User-Agent': bs.getEnvironment()['userAgentString']}
            if self._requestType != "get" or self._data:
                if self._requestType == 'get':
                    if self._data:
                        request = urllib2.Request(self._request + '?' + urllib.urlencode(self._data), None, env)
                    else:
                        request = urllib2.Request(self._request, None, env)
                elif self._requestType == 'post':
                    request = urllib2.Request(self._request, json.dumps(self._data), env)
                else:
                    raise RuntimeError("Invalid requestType: " + self._requestType)
                response = urllib2.urlopen(request)
            else:
                response = urllib2.urlopen(self._request)

            if self._eval_data:
                responseData = json.loads(response.read())
            else:
                responseData = response.read()
            if self._callback is not None:
                bs.callInGameThread(bs.Call(self._runCallback, responseData, response.getcode()))

        except:
            bs.printException()
            if self._callback is not None:
                bs.callInGameThread(bs.Call(self._runCallback, None, None))


def mm_serverGet(request, data, callback=None, eval_data=True):
    ModManager_ServerCallThread(request, 'get', data, callback, eval_data=eval_data).start()


def mm_serverPost(request, data, callback=None, eval_data=True):
    ModManager_ServerCallThread(request, 'post', data, callback, eval_data=eval_data).start()


class ModManagerWindow(Window):
    _selectedMod, _selectedModIndex = None, None
    categories = set(["all"])
    tabs = []
    tabheight = 35
    mods = []
    _modWidgets = []
    currently_fetching = False
    timers = {}

    def __init__(self, transition='inRight', modal=False, showTab="all", onCloseCall=None, backLocationCls=None, originWidget=None):

        # if they provided an origin-widget, scale up from that
        if originWidget is not None:
            self._transitionOut = 'outScale'
            transition = 'inScale'
        else:
            self._transitionOut = 'outRight'

        self._backLocationCls = backLocationCls
        self._onCloseCall = onCloseCall
        self._showTab = showTab
        self._selectedTab = {'label': showTab}
        if showTab != "all":
            def check_tab_available():
                if not self._rootWidget.exists():
                    return
                if any([mod.category == showTab for mod in self.mods]):
                    return
                if "button" in self._selectedTab:
                    return
                self._selectedTab = {"label": "all"}
                self._refresh()
            self.timers["check_tab_available"] = bs.Timer(300, check_tab_available, timeType='real')
        self._modal = modal

        self._windowTitleName = "Community Mod Manager"

        def sort_rating(mods):
            mods = sorted(mods, key=lambda mod: mod.rating_submissions, reverse=True)
            return sorted(mods, key=lambda mod: mod.rating, reverse=True)

        def sort_downloads(mods):
            return sorted(mods, key=lambda mod: mod.downloads, reverse=True)

        def sort_alphabetical(mods):
            return sorted(mods, key=lambda mod: mod.name.lower())

        _sortModes = [
            ('Rating', sort_rating, lambda m: stats_cached()),
            ('Downloads', sort_downloads, lambda m: stats_cached()),
            ('Alphabetical', sort_alphabetical),
        ]

        self.sortModes = {}
        for i, sortMode in enumerate(_sortModes):
            name, func = sortMode[:2]
            next_sortMode = _sortModes[(i + 1) % len(_sortModes)]
            condition = sortMode[2] if len(sortMode) > 2 else (lambda mods: True)
            self.sortModes[name] = {
                'func': func,
                'condition': condition,
                'next': next_sortMode[0],
                'name': name,
                'index': i,
            }

        sortMode = config.get('sortMode')
        if not sortMode or sortMode not in self.sortModes:
            sortMode = _sortModes[0][0]
        self.sortMode = self.sortModes[sortMode]

        self._width = 650
        self._height = 380 if gSmallUI else 420 if gMedUI else 500
        topExtra = 20 if gSmallUI else 0

        self._rootWidget = ContainerWidget(size=(self._width, self._height + topExtra), transition=transition,
                                           scale=2.05 if gSmallUI else 1.5 if gMedUI else 1.0,
                                           stackOffset=(0, -10) if gSmallUI else (0, 0))

        self._backButton = backButton = ButtonWidget(parent=self._rootWidget, position=(self._width - 160, self._height - 60),
                                                     size=(160, 68), scale=0.77,
                                                     autoSelect=True, textScale=1.3,
                                                     label=bs.Lstr(resource='doneText' if self._modal else 'backText'),
                                                     onActivateCall=self._back)
        self._rootWidget.cancelButton = backButton
        TextWidget(parent=self._rootWidget, position=(0, self._height - 47),
                   size=(self._width, 25),
                   text=self._windowTitleName, color=gHeadingColor,
                   maxWidth=290,
                   hAlign="center", vAlign="center")

        v = self._height - 59
        h = 41
        bColor = (0.6, 0.53, 0.63)
        bTextColor = (0.75, 0.7, 0.8)

        s = 1.1 if gSmallUI else 1.27 if gMedUI else 1.57
        v -= 63.0 * s
        self.refreshButton = ButtonWidget(parent=self._rootWidget,
                                          position=(h, v),
                                          size=(90, 58.0 * s),
                                          onActivateCall=bs.Call(self._cb_refresh, force_fresh=True),
                                          color=bColor,
                                          autoSelect=True,
                                          buttonType='square',
                                          textColor=bTextColor,
                                          textScale=0.7,
                                          label="Reload List")

        v -= 63.0 * s
        self.modInfoButton = ButtonWidget(parent=self._rootWidget, position=(h, v), size=(90, 58.0 * s),
                                          onActivateCall=bs.Call(self._cb_info),
                                          color=bColor,
                                          autoSelect=True,
                                          textColor=bTextColor,
                                          buttonType='square',
                                          textScale=0.7,
                                          label="Mod Info")

        v -= 63.0 * s
        self.sortButtonData = {"s": s, "h": h, "v": v, "bColor": bColor, "bTextColor": bTextColor}
        self.sortButton = ButtonWidget(parent=self._rootWidget, position=(h, v), size=(90, 58.0 * s),
                                       onActivateCall=bs.Call(self._cb_sorting),
                                       color=bColor,
                                       autoSelect=True,
                                       textColor=bTextColor,
                                       buttonType='square',
                                       textScale=0.7,
                                       label="Sorting:\n" + self.sortMode['name'])

        v -= 63.0 * s
        self.settingsButton = ButtonWidget(parent=self._rootWidget, position=(h, v), size=(90, 58.0 * s),
                                           onActivateCall=bs.Call(self._cb_settings),
                                           color=bColor,
                                           autoSelect=True,
                                           textColor=bTextColor,
                                           buttonType='square',
                                           textScale=0.7,
                                           label="Settings")

        v = self._height - 75
        self.columnPosY = self._height - 75 - self.tabheight
        self._scrollHeight = self._height - 119 - self.tabheight
        scrollWidget = ScrollWidget(parent=self._rootWidget, position=(140, self.columnPosY - self._scrollHeight),
                                    size=(self._width - 180, self._scrollHeight + 10))
        backButton.set(downWidget=scrollWidget, leftWidget=scrollWidget)
        self._columnWidget = ColumnWidget(parent=scrollWidget)

        for b in [self.refreshButton, self.modInfoButton, self.settingsButton]:
            b.rightWidget = scrollWidget
        scrollWidget.leftWidget = self.refreshButton

        self._cb_refresh()

        backButton.onActivateCall = self._back
        self._rootWidget.startButton = backButton
        self._rootWidget.onCancelCall = backButton.activate
        self._rootWidget.selectedChild = scrollWidget

    def _refresh(self, refreshTabs=True):
        while len(self._modWidgets) > 0:
            self._modWidgets.pop().delete()

        for mod in self.mods:
            if mod.category:
                self.categories.add(mod.category)
        if refreshTabs:
            self._refreshTabs()

        while not self.sortMode['condition'](self.mods):
            self.sortMode = self.sortModes[self.sortMode['next']]
            self.sortButton.label = "Sorting:\n" + self.sortMode['name']

        self.mods = self.sortMode["func"](self.mods)
        visible = self.mods[:]
        if self._selectedTab["label"] != "all":
            visible = [m for m in visible if m.category == self._selectedTab["label"]]

        for index, mod in enumerate(visible):
            color = (0.6, 0.6, 0.7, 1.0)
            if mod.is_installed():
                color = (0.85, 0.85, 0.85, 1)
                if mod.checkUpdate():
                    if mod.is_outdated():
                        color = (0.85, 0.3, 0.3, 1)
                    else:
                        color = (1, 0.84, 0, 1)

            w = TextWidget(parent=self._columnWidget, size=(self._width - 40, 24),
                           maxWidth=self._width - 110,
                           text=mod.name,
                           hAlign='left', vAlign='center',
                           color=color,
                           alwaysHighlight=True,
                           onSelectCall=bs.Call(self._cb_select, index, mod),
                           onActivateCall=bs.Call(self._cb_info, True),
                           selectable=True)
            w.showBufferTop = 50
            w.showBufferBottom = 50
            # hitting up from top widget shoud jump to 'back;
            if index == 0:
                tab_button = self.tabs[int((len(self.tabs) - 1) / 2)]["button"]
                w.upWidget = tab_button

            if self._selectedMod and mod.filename == self._selectedMod.filename:
                self._columnWidget.set(selectedChild=w, visibleChild=w)

            self._modWidgets.append(w)

    def _refreshTabs(self):
        if not self._rootWidget.exists():
            return
        for t in self.tabs:
            for widget in t.values():
                if isinstance(widget, bs.Widget) or isinstance(widget, Widget):
                    widget.delete()
        self.tabs = []
        total = len(self.categories)
        columnWidth = self._width - 180
        tabWidth = 100
        tabSpacing = 12
        # _______/-minigames-\_/-utilities-\_______
        for i, tab in enumerate(sorted(list(self.categories))):
            px = 140 + columnWidth / 2 - tabWidth * total / 2 + tabWidth * i
            pos = (px, self.columnPosY + 5)
            size = (tabWidth - tabSpacing, self.tabheight + 10)
            rad = 10
            center = (pos[0] + 0.1 * size[0], pos[1] + 0.9 * size[1])
            txt = TextWidget(parent=self._rootWidget, position=center, size=(0, 0),
                             hAlign='center', vAlign='center',
                             maxWidth=1.4 * rad, scale=0.6, shadow=1.0, flatness=1.0)
            button = ButtonWidget(parent=self._rootWidget, position=pos, autoSelect=True,
                                  buttonType='tab', size=size, label=tab, enableSound=False,
                                  onActivateCall=bs.Call(self._cb_select_tab, i),
                                  color=(0.52, 0.48, 0.63), textColor=(0.65, 0.6, 0.7))
            self.tabs.append({'text': txt,
                              'button': button,
                              'label': tab})

        for i, tab in enumerate(self.tabs):
            if self._selectedTab["label"] == tab["label"]:
                self._cb_select_tab(i, refresh=False)

    def _cb_select_tab(self, index, refresh=True):
        bs.playSound(bs.getSound('click01'))
        self._selectedTab = self.tabs[index]

        for i, tab in enumerate(self.tabs):
            button = tab["button"]
            if i == index:
                button.set(color=(0.5, 0.4, 0.93), textColor=(0.85, 0.75, 0.95))  # lit
            else:
                button.set(color=(0.52, 0.48, 0.63), textColor=(0.65, 0.6, 0.7))  # unlit
        if refresh:
            self._refresh(refreshTabs=False)

    def _cb_select(self, index, mod):
        self._selectedModIndex = index
        self._selectedMod = mod

    def _cb_refresh(self, force_fresh=False):
        self.mods = []
        localfiles = os.listdir(bs.getEnvironment()['userScriptsDirectory'] + "/")
        for file in localfiles:
            if file.endswith(".py"):
                self.mods.append(LocalMod(file))

        # if CHECK_FOR_UPDATES:
        #     for mod in self.mods:
        #         if mod.checkUpdate():
        #             bs.screenMessage('Update available for ' + mod.filename)
        #             UpdateModWindow(mod, self._cb_refresh)

        self._refresh()
        self.currently_fetching = True

        def f(*args, **kwargs):
            kwargs["force_fresh"] = force_fresh
            self._cb_serverdata(*args, **kwargs)
        get_index(f, force_fresh=force_fresh)
        self.timers["showFetchingIndicator"] = bs.Timer(500, bs.WeakCall(self._showFetchingIndicator), timeType='real')

    def _cb_serverdata(self, data, status_code, force_fresh=False):
        if not self._rootWidget.exists():
            return
        self.currently_fetching = False
        if data:
            m, v = process_server_data(data)
            # when we got network add the network mods
            localMods = self.mods[:]
            netMods = [Mod(d) for d in m.values()]
            self.mods = netMods
            netFilenames = [m.filename for m in netMods]
            for localmod in localMods:
                if localmod.filename not in netFilenames:
                    self.mods.append(localmod)
            for mod in self.mods:
                mod._mods = {m.base: m for m in self.mods}
            self._refresh()
        else:
            bs.screenMessage('network error :(')
        fetch_stats(self._cb_stats, force_fresh=force_fresh)

    def _cb_stats(self, data, status_code):
        if not self._rootWidget.exists() or not data:
            return

        def fill_mods_with(d, attr):
            for mod_id, value in d.items():
                for mod in self.mods:
                    if mod.base == mod_id:
                        setattr(mod, attr, value)

        fill_mods_with(data.get('average_ratings', {}), 'rating')
        fill_mods_with(data.get('own_ratings', {}), 'own_rating')
        fill_mods_with(data.get('amount_ratings', {}), 'rating_submissions')
        fill_mods_with(data.get('downloads', {}), 'downloads')

        self._refresh()

    def _showFetchingIndicator(self):
        if self.currently_fetching:
            bs.screenMessage("loading...")

    def _cb_info(self, withSound=False):
        if withSound:
            bs.playSound(bs.getSound('swish'))
        ModInfoWindow(self._selectedMod, self, originWidget=self.modInfoButton)

    def _cb_settings(self):
        SettingsWindow(self._selectedMod, self, originWidget=self.settingsButton)

    def _cb_sorting(self):
        self.sortMode = self.sortModes[self.sortMode['next']]
        while not self.sortMode['condition'](self.mods):
            self.sortMode = self.sortModes[self.sortMode['next']]
        config['sortMode'] = self.sortMode['name']
        bs.writeConfig()
        self.sortButton.label = "Sorting:\n" + self.sortMode['name']
        self._cb_refresh()

    def _back(self):
        self._rootWidget.doTransition(self._transitionOut)
        if not self._modal:
            uiGlobals['mainMenuWindow'] = self._backLocationCls(transition='inLeft').getRootWidget()
        if self._onCloseCall is not None:
            self._onCloseCall()


class UpdateModWindow(Window):

    def __init__(self, mod, onok, swish=True, back=False):
        self._back = back
        self.mod = mod
        self.onok = bs.WeakCall(onok)
        if swish:
            bs.playSound(bs.getSound('swish'))
        text = "Do you want to update %s?" if mod.is_installed() else "Do you want to install %s?"
        text = text % (mod.filename)
        if mod.changelog and mod.is_installed():
            text += "\n\nChangelog:"
            for change in mod.changelog:
                text += "\n" + change
        height = 100 * (1 + len(mod.changelog) * 0.3) if mod.is_installed() else 100
        width = 360 * (1 + len(mod.changelog) * 0.15) if mod.is_installed() else 360
        self._rootWidget = ConfirmWindow(text, self.ok, height=height, width=width).getRootWidget()

    def ok(self):
        self.mod.install(lambda mod, success: self.onok())


class DeleteModWindow(Window):

    def __init__(self, mod, onok, swish=True, back=False):
        self._back = back
        self.mod = mod
        self.onok = bs.WeakCall(onok)
        if swish:
            bs.playSound(bs.getSound('swish'))

        self._rootWidget = ConfirmWindow("Are you sure you want to delete " + mod.filename, self.ok).getRootWidget()

    def ok(self):
        self.mod.delete(self.onok)
        QuitToApplyWindow()


class RateModWindow(Window):
    levels = ["Poor", "Below Average", "Average", "Above Average", "Excellent"]
    icons = ["trophy0b", "trophy1", "trophy2", "trophy3", "trophy4"]

    def __init__(self, mod, onok, swish=True, back=False):
        self._back = back
        self.mod = mod
        self.onok = onok
        if swish:
            bs.playSound(bs.getSound('swish'))
        text = "How do you want to rate {}?".format(mod.name)

        okText = bs.Lstr(resource='okText')
        cancelText = bs.Lstr(resource='cancelText')
        width = 360
        height = 330

        self._rootWidget = ContainerWidget(size=(width, height), transition='inRight',
                                           scale=2.1 if gSmallUI else 1.5 if gMedUI else 1.0)

        TextWidget(parent=self._rootWidget, position=(width * 0.5, height - 30), size=(0, 0),
                   hAlign="center", vAlign="center", text=text, maxWidth=width * 0.9, maxHeight=height - 75)

        b = ButtonWidget(parent=self._rootWidget, autoSelect=True, position=(20, 20), size=(150, 50), label=cancelText, onActivateCall=self._cancel)
        self._rootWidget.set(cancelButton=b)
        okButtonH = width - 175

        b = ButtonWidget(parent=self._rootWidget, autoSelect=True, position=(okButtonH, 20), size=(150, 50), label=okText, onActivateCall=self._ok)

        self._rootWidget.set(selectedChild=b, startButton=b)

        columnPosY = height - 75
        _scrollHeight = height - 150

        scrollWidget = ScrollWidget(parent=self._rootWidget, position=(20, columnPosY - _scrollHeight), size=(width - 40, _scrollHeight + 10))
        columnWidget = ColumnWidget(parent=scrollWidget)

        self._rootWidget.set(selectedChild=columnWidget)

        self.selected = self.mod.own_rating or 2
        for num, name in enumerate(self.levels):
            s = bs.getSpecialChar(self.icons[num]) + name
            w = TextWidget(parent=columnWidget, size=(width - 40, 24 + 8),
                           maxWidth=width - 110,
                           text=s,
                           scale=0.85,
                           hAlign='left', vAlign='center',
                           alwaysHighlight=True,
                           onSelectCall=bs.Call(self._select, num),
                           onActivateCall=bs.Call(self._ok),
                           selectable=True)
            w.showBufferTop = 50
            w.showBufferBottom = 50

            if num == self.selected:
                columnWidget.set(selectedChild=w, visibleChild=w)
                self._rootWidget.set(selectedChild=w)
            elif num == 4:
                w.downWidget = b

    def _select(self, index):
        self.selected = index

    def _cancel(self):
        self._rootWidget.doTransition('outRight')

    def _ok(self):
        if not self._rootWidget.exists():
            return
        self._rootWidget.doTransition('outLeft')
        self.onok(self.selected)


class QuitToApplyWindow(Window):

    def __init__(self):
        global quittoapply
        if quittoapply is not None:
            quittoapply.delete()
            quittoapply = None
        bs.playSound(bs.getSound('swish'))
        text = "Quit BS to reload mods?"
        if bs.getEnvironment()["platform"] == "android":
            text += "\n(On Android you have to close the activity)"
        self._rootWidget = quittoapply = ConfirmWindow(text, self._doFadeAndQuit).getRootWidget()

    def _doFadeAndQuit(self):
        # FIXME: using protected apis
        bsInternal._fadeScreen(False, time=200, endCall=bs.Call(bs.quit, soft=True))
        bsInternal._lockAllInput()
        # unlock and fade back in shortly.. just in case something goes wrong
        # (or on android where quit just backs out of our activity and we may come back)
        bs.realTimer(300, bsInternal._unlockAllInput)
        # bs.realTimer(300, bs.Call(bsInternal._fadeScreen,True))


class ModInfoWindow(Window):
    def __init__(self, mod, modManagerWindow, originWidget=None):
        # TODO: cleanup
        self.modManagerWindow = modManagerWindow
        self.mod = mod
        s = 1.1 if gSmallUI else 1.27 if gMedUI else 1.57
        bColor = (0.6, 0.53, 0.63)
        bTextColor = (0.75, 0.7, 0.8)
        width = 360 * s
        height = 40 + 100 * s
        if mod.author:
            height += 25
        if not mod.isLocal:
            height += 50
        if mod.rating is not None:
            height += 50
        if mod.downloads:
            height += 50

        buttons = sum([(mod.checkUpdate() or not mod.is_installed()), mod.is_installed(), mod.is_installed(), True])

        color = (1, 1, 1)
        textScale = 0.7 * s

        # if they provided an origin-widget, scale up from that
        if originWidget is not None:
            self._transitionOut = 'outScale'
            scaleOrigin = originWidget.getScreenSpaceCenter()
            transition = 'inScale'
        else:
            self._transitionOut = None
            scaleOrigin = None
            transition = 'inRight'

        self._rootWidget = ContainerWidget(size=(width, height), transition=transition,
                                           scale=2.1 if gSmallUI else 1.5 if gMedUI else 1.0,
                                           scaleOriginStackOffset=scaleOrigin)

        pos = height * 0.9
        labelspacing = height / (7.0 if (mod.rating is None and not mod.downloads) else 7.5)

        if mod.tag:
            TextWidget(parent=self._rootWidget, position=(width * 0.49, pos), size=(0, 0),
                       hAlign="right", vAlign="center", text=mod.name, scale=textScale * 1.5,
                       color=color, maxWidth=width * 0.9, maxHeight=height - 75)
            TextWidget(parent=self._rootWidget, position=(width * 0.51, pos - labelspacing * 0.1),
                       hAlign="left", vAlign="center", text=mod.tag, scale=textScale * 0.9,
                       color=(1, 0.3, 0.3), big=True, size=(0, 0))
        else:
            TextWidget(parent=self._rootWidget, position=(width * 0.5, pos), size=(0, 0),
                       hAlign="center", vAlign="center", text=mod.name, scale=textScale * 1.5,
                       color=color, maxWidth=width * 0.9, maxHeight=height - 75)

        pos -= labelspacing

        if mod.author:
            TextWidget(parent=self._rootWidget, position=(width * 0.5, pos), size=(0, 0),
                       hAlign="center", vAlign="center", text="by " + mod.author, scale=textScale,
                       color=color, maxWidth=width * 0.9, maxHeight=height - 75)
            pos -= labelspacing
        if not mod.isLocal:
            if mod.checkUpdate():
                if mod.is_outdated():
                    status = "update available"
                else:
                    status = "unrecognized version"
            else:
                status = "installed"
            if not mod.is_installed():
                status = "not installed"
            TextWidget(parent=self._rootWidget, position=(width * 0.45, pos), size=(0, 0),
                       hAlign="right", vAlign="center", text="Status:", scale=textScale,
                       color=color, maxWidth=width * 0.9, maxHeight=height - 75)
            status = TextWidget(parent=self._rootWidget, position=(width * 0.55, pos), size=(0, 0),
                                hAlign="left", vAlign="center", text=status, scale=textScale,
                                color=color, maxWidth=width * 0.9, maxHeight=height - 75)
            pos -= labelspacing * 0.775

        if mod.downloads:
            TextWidget(parent=self._rootWidget, position=(width * 0.45, pos), size=(0, 0),
                       hAlign="right", vAlign="center", text="Downloads:", scale=textScale,
                       color=color, maxWidth=width * 0.9, maxHeight=height - 75)
            TextWidget(parent=self._rootWidget, position=(width * 0.55, pos), size=(0, 0),
                       hAlign="left", vAlign="center", text=str(mod.downloads), scale=textScale,
                       color=color, maxWidth=width * 0.9, maxHeight=height - 75)
            pos -= labelspacing * 0.775

        if mod.rating is not None:
            TextWidget(parent=self._rootWidget, position=(width * 0.45, pos), size=(0, 0),
                       hAlign="right", vAlign="center", text="Rating:", scale=textScale,
                       color=color, maxWidth=width * 0.9, maxHeight=height - 75)
            rating_str = bs.getSpecialChar(RateModWindow.icons[mod.rating]) + RateModWindow.levels[mod.rating]
            TextWidget(parent=self._rootWidget, position=(width * 0.4725, pos), size=(0, 0),
                       hAlign="left", vAlign="center", text=rating_str, scale=textScale,
                       color=color, maxWidth=width * 0.9, maxHeight=height - 75)
            pos -= labelspacing * 0.775
            submissions = "({} {})".format(mod.rating_submissions, "submission" if mod.rating_submissions < 2 else "submissions")
            TextWidget(parent=self._rootWidget, position=(width * 0.4725, pos), size=(0, 0),
                       hAlign="left", vAlign="center", text=submissions, scale=textScale,
                       color=color, maxWidth=width * 0.9, maxHeight=height - 75)
            pos += labelspacing * 0.3

        if not mod.author and mod.isLocal:
            pos -= labelspacing

        if not (gSmallUI or gMedUI):
            pos -= labelspacing * 0.25

        pos -= labelspacing * 2.55

        self.button_index = -1

        def button_pos():
            self.button_index += 1
            d = {
                1: [0.5],
                2: [0.3, 0.7],
                3: [0.2, 0.45, 0.8],
                4: [0.17, 0.390, 0.61, 0.825],
            }
            x = width * d[buttons][self.button_index]
            y = pos
            sx, sy = button_size()
            x -= sx / 2
            y += sy / 2
            return x, y

        def button_size():
            sx = {1: 100, 2: 80, 3: 80, 4: 75}[buttons] * s
            sy = 40 * s
            return sx, sy

        def button_text_size():
            return {1: 0.8, 2: 1.0, 3: 1.2, 4: 1.2}[buttons]

        if mod.checkUpdate() or not mod.is_installed():
            text = "Download Mod"
            if mod.is_outdated():
                text = "Update Mod"
            elif mod.checkUpdate():
                text = "Reset Mod"
            self.downloadButton = ButtonWidget(parent=self._rootWidget,
                                               position=button_pos(), size=button_size(),
                                               onActivateCall=bs.Call(self._download,),
                                               color=bColor,
                                               autoSelect=True,
                                               textColor=bTextColor,
                                               buttonType='square',
                                               textScale=button_text_size(),
                                               label=text)

        if mod.is_installed():
            self.deleteButton = ButtonWidget(parent=self._rootWidget,
                                             position=button_pos(), size=button_size(),
                                             onActivateCall=bs.Call(self._delete),
                                             color=bColor,
                                             autoSelect=True,
                                             textColor=bTextColor,
                                             buttonType='square',
                                             textScale=button_text_size(),
                                             label="Delete Mod")

            self.rateButton = ButtonWidget(parent=self._rootWidget,
                                           position=button_pos(), size=button_size(),
                                           onActivateCall=bs.Call(self._rate),
                                           color=bColor,
                                           autoSelect=True,
                                           textColor=bTextColor,
                                           buttonType='square',
                                           textScale=button_text_size(),
                                           label="Rate Mod" if mod.own_rating is None else "Change Rating")

        okButtonSize = button_size()
        okButtonPos = button_pos()
        okText = bs.Lstr(resource='okText')
        b = ButtonWidget(parent=self._rootWidget, autoSelect=True, position=okButtonPos, size=okButtonSize, label=okText, onActivateCall=self._ok)

        self._rootWidget.onCancelCall = b.activate
        self._rootWidget.selectedChild = b
        self._rootWidget.startButton = b

    def _ok(self):
        self._rootWidget.doTransition('outLeft' if self._transitionOut is None else self._transitionOut)

    def _delete(self):
        DeleteModWindow(self.mod, self.modManagerWindow._cb_refresh)
        self._ok()

    def _download(self):
        UpdateModWindow(self.mod, self.modManagerWindow._cb_refresh)
        self._ok()

    def _rate(self):

        def submit_cb():
            self.modManagerWindow._cb_refresh(force_fresh=True)

        def cb(rating):
            submit_mod_rating(self.mod, rating, submit_cb)

        RateModWindow(self.mod, cb)
        self._ok()


class SettingsWindow(Window):
    def __init__(self, mod, modManagerWindow, originWidget=None):
        self.modManagerWindow = modManagerWindow
        self.mod = mod
        s = 1.1 if gSmallUI else 1.27 if gMedUI else 1.57
        bTextColor = (0.75, 0.7, 0.8)
        width = 380 * s
        height = 240 * s
        textScale = 0.7 * s

        # if they provided an origin-widget, scale up from that
        if originWidget is not None:
            self._transitionOut = 'outScale'
            scaleOrigin = originWidget.getScreenSpaceCenter()
            transition = 'inScale'
        else:
            self._transitionOut = None
            scaleOrigin = None
            transition = 'inRight'

        self._rootWidget = ContainerWidget(size=(width, height), transition=transition,
                                           scale=2.1 if gSmallUI else 1.5 if gMedUI else 1.0,
                                           scaleOriginStackOffset=scaleOrigin)

        self._titleText = TextWidget(parent=self._rootWidget, position=(0, height - 52),
                                     size=(width, 30), text="ModManager Settings", color=(1.0, 1.0, 1.0),
                                     hAlign="center", vAlign="top", scale=1.5 * textScale)

        pos = height * 0.65
        TextWidget(parent=self._rootWidget, position=(width * 0.35, pos), size=(0, 40),
                   hAlign="right", vAlign="center",
                   text="Branch:", scale=textScale,
                   color=bTextColor, maxWidth=width * 0.9, maxHeight=(height - 75))
        self.branch = TextWidget(parent=self._rootWidget, position=(width * 0.4, pos),
                                 size=(width * 0.4, 40), text=config.get("branch", "master"),
                                 hAlign="left", vAlign="center",
                                 editable=True, padding=4,
                                 onReturnPressCall=self.setBranch)

        pos -= height * 0.125
        checkUpdatesValue = config.get("submit-download-statistics", True)
        self.downloadStats = CheckBoxWidget(parent=self._rootWidget, text="submit download statistics",
                                            position=(width * 0.2, pos), size=(170, 30),
                                            textColor=(0.8, 0.8, 0.8),
                                            value=checkUpdatesValue,
                                            onValueChangeCall=self.setDownloadStats)

        pos -= height * 0.125
        checkUpdatesValue = config.get("auto-check-updates", True)
        self.checkUpdates = CheckBoxWidget(parent=self._rootWidget, text="automatically check for updates",
                                           position=(width * 0.2, pos), size=(170, 30),
                                           textColor=(0.8, 0.8, 0.8),
                                           value=checkUpdatesValue,
                                           onValueChangeCall=self.setCheckUpdate)

        pos -= height * 0.125
        autoUpdatesValue = config.get("auto-update-old-mods", True)
        self.autoUpdates = CheckBoxWidget(parent=self._rootWidget, text="auto-update outdated mods",
                                          position=(width * 0.2, pos), size=(170, 30),
                                          textColor=(0.8, 0.8, 0.8),
                                          value=autoUpdatesValue,
                                          onValueChangeCall=self.setAutoUpdate)
        self.checkAutoUpdateState()

        okButtonSize = (150, 50)
        okButtonPos = (width * 0.5 - okButtonSize[0] / 2, 20)
        okText = bs.Lstr(resource='okText')
        okButton = ButtonWidget(parent=self._rootWidget, position=okButtonPos, size=okButtonSize, label=okText, onActivateCall=self._ok)

        self._rootWidget.set(onCancelCall=okButton.activate, selectedChild=okButton, startButton=okButton)

    def _ok(self):
        if self.branch.text() != config.get("branch", "master"):
            self.setBranch()
        self._rootWidget.doTransition('outLeft' if self._transitionOut is None else self._transitionOut)

    def setBranch(self):
        branch = self.branch.text()
        if branch == '':
            branch = "master"
        bs.screenMessage("fetching branch '" + branch + "'")

        def cb(data, status_code):
            newBranch = branch
            if data:
                bs.screenMessage('ok')
            else:
                bs.screenMessage('failed to fetch branch')
                newBranch = "master"
            bs.screenMessage("set branch to " + newBranch)
            config["branch"] = newBranch
            bs.writeConfig()
            self.modManagerWindow._cb_refresh()

        get_index(cb, branch=branch)

    def setCheckUpdate(self, val):
        config["auto-check-updates"] = bool(val)
        bs.writeConfig()
        self.checkAutoUpdateState()

    def checkAutoUpdateState(self):
        if not self.checkUpdates.value:
            # FIXME: properly disable checkbox
            self.autoUpdates.set(value=False,
                                 color=(0.65, 0.65, 0.65),
                                 textColor=(0.65, 0.65, 0.65))
        else:
            # FIXME: match original color
            autoUpdatesValue = config.get("auto-update-old-mods", True)
            self.autoUpdates.set(value=autoUpdatesValue,
                                 color=(0.475, 0.6, 0.2),
                                 textColor=(0.8, 0.8, 0.8))

    def setAutoUpdate(self, val):
        # FIXME: properly disable checkbox
        if not self.checkUpdates.value:
            bs.playSound(bs.getSound("error"))
            self.autoUpdates.value = False
            return
        config["auto-update-old-mods"] = bool(val)
        bs.writeConfig()

    def setDownloadStats(self, val):
        config["submit-download-statistics"] = bool(val)
        bs.writeConfig()


class Mod:
    name = False
    author = None
    filename = None
    base = None
    changelog = []
    old_md5s = []
    url = False
    isLocal = False
    category = None
    requires = []
    supports = []
    rating = None
    rating_submissions = 0
    own_rating = None
    downloads = None
    tag = None
    data = None

    def __init__(self, d):
        self.data = d
        self.author = d.get('author')
        if 'filename' in d:
            self.filename = d['filename']
            self.base = self.filename[:-3]
        else:
            raise RuntimeError('mod without filename')
        if 'name' in d:
            self.name = d['name']
        else:
            self.name = self.filename
        if 'md5' in d:
            self.md5 = d['md5']
        else:
            raise RuntimeError('mod without md5')

        self.changelog = d.get('changelog', [])
        self.old_md5s = d.get('old_md5s', [])
        self.category = d.get('category', None)
        self.requires = d.get('requires', [])
        self.supports = d.get('supports', [])
        self.tag = d.get('tag', None)

    def writeData(self, callback, doQuitWindow, data, status_code):
        path = bs.getEnvironment()['userScriptsDirectory'] + "/" + self.filename

        if data:
            if self.is_installed():
                os.rename(path, path + ".bak")  # rename the old file to be able to recover it if something goes wrong
            with open(path, 'w') as f:
                f.write(data)
        else:
            bs.screenMessage("Failed to write mod")

        if callback:
            callback(self, data is not None)
        if doQuitWindow:
            QuitToApplyWindow()

        submit_download(self)

    def install(self, callback, doQuitWindow=True):
        def check_deps_and_install(mod=None, succeded=True):
            if any([dep not in self._mods for dep in self.requires]):
                raise Exception("dependency inconsistencies")
            if not all([self._mods[dep].up_to_date() for dep in self.requires]) or not succeded:
                return

            fetch_mod(self.data, partial(self.writeData, callback, doQuitWindow))
        if len(self.requires) < 1:
            check_deps_and_install()
        else:
            for dep in self.requires:
                bs.screenMessage(self.name + " requires " + dep + "; installing...")
                if not self._mods:
                    raise Exception("missing mod._mods")
                if dep not in self._mods:
                    raise Exception("dependency inconsistencies (missing " + dep + ")")
                self._mods[dep].install(check_deps_and_install, False)

    @property
    def ownData(self):
        path = bs.getEnvironment()['userScriptsDirectory'] + "/" + self.filename
        if os.path.exists(path):
            with open(path, "r") as ownFile:
                return ownFile.read()

    def delete(self, cb=None):
        path = bs.getEnvironment()['userScriptsDirectory'] + "/" + self.filename
        os.rename(path, path + ".bak")  # rename the old file to be able to recover it if something goes wrong
        if os.path.exists(path + "c"): # check for python bytecode
            os.remove(path + "c")  # remove python bytecode because importing still works without .py file
        if cb:
            cb()

    def checkUpdate(self):
        if not self.is_installed():
            return False
        if self.local_md5() != self.md5:
            return True
        return False

    def up_to_date(self):
        return self.is_installed() and self.local_md5() == self.md5

    def is_installed(self):
        return os.path.exists(bs.getEnvironment()['userScriptsDirectory'] + "/" + self.filename)

    def local_md5(self):
        return md5(self.ownData).hexdigest()

    def is_outdated(self):
        if not self.old_md5s or not self.is_installed():
            return False
        local_md5 = self.local_md5()
        for old_md5 in self.old_md5s:
            if local_md5.startswith(old_md5):
                return True
        return False


class LocalMod(Mod):
    isLocal = True

    def __init__(self, filename):
        self.filename = filename
        self.base = self.filename[:-3]
        self.name = filename + " (Local Only)"
        with open(bs.getEnvironment()['userScriptsDirectory'] + "/" + filename, "r") as ownFile:
            self.ownData = ownFile.read()

    def checkUpdate(self):
        return False

    def is_installed(self):
        return True

    def up_to_date(self):
        return True

    def getData(self):
        return False

    def writeData(self, data=None):
        bs.screenMessage("Can't update local-only mod!")


_setTabOld = StoreWindow._setTab


def _setTab(self, tab):
    _setTabOld(self, tab)
    if hasattr(self, "_getMoreGamesButton"):
        if self._getMoreGamesButton.exists():
            self._getMoreGamesButton.delete()
    if tab == "minigames":
        self._getMoreGamesButton = bs.buttonWidget(parent=self._rootWidget, autoSelect=True,
                                                   label=bs.Lstr(resource='addGameWindow.getMoreGamesText'),
                                                   color=(0.54, 0.52, 0.67),
                                                   textColor=(0.7, 0.65, 0.7),
                                                   onActivateCall=self._onGetMoreGamesPress,
                                                   size=(178, 50), position=(70, 60))
        # TODO: transitions


def _onGetMoreGamesPress(self):
    if not self._modal:
        bs.containerWidget(edit=self._rootWidget, transition='outLeft')
    mm_window = ModManagerWindow(modal=self._modal, backLocationCls=self.__class__, showTab="minigames")
    if not self._modal:
        uiGlobals['mainMenuWindow'] = mm_window.getRootWidget()

StoreWindow._setTab = _setTab
StoreWindow._onGetMoreGamesPress = _onGetMoreGamesPress