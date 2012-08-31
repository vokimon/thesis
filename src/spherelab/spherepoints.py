#!/usr/bin/python

from PySide import QtCore, QtGui, QtOpenGL
from PySide.QtCore import Qt
import sys
import numpy as np
import time
from OpenGL import GL, GLU
import math

from colorfield import ColorField, Reloader

def ead2xyz(e,a,d) :
	ra, re = math.radians(a), math.radians(e)
	sa, se = math.sin(ra), math.sin(re)
	ca, ce = math.cos(ra), math.cos(re)
	x,y,z = d*ce*ca, d*ce*sa, d*se
	return [x,y,z]

def cartesian_product(*arrays):
	import operator
	broadcastable = np.ix_(*arrays)
	broadcasted = np.broadcast_arrays(*broadcastable)
	rows, cols = reduce(operator.mul, broadcasted[0].shape), len(broadcasted)
	out = np.empty(rows * cols, dtype=broadcasted[0].dtype)
	start, end = 0, rows
	for a in broadcasted:
		out[start:end] = a.reshape(-1)
		start, end = end, end + rows
	return out.reshape(cols, rows).T

class TrackBall(object) :
	def __init__(self, angularVelocity=0., axis=QtGui.QVector3D(0,1,0)) :
		self._angularVelocity = angularVelocity
		self._rotation = QtGui.QQuaternion()
		self._paused = False
		self._pressed = False
		self._lastTime = QtCore.QTime.currentTime()
		self._axis = axis

	def rotation(self) :
		if self._paused or self._pressed : return self._rotation
		currentTime = QtCore.QTime.currentTime()
		angle = self._angularVelocity * self._lastTime.msecsTo(currentTime)
		return QtGui.QQuaternion.fromAxisAndAngle(self._axis, angle) * self._rotation

	def push(self, point, reference) :
		self._rotation = self.rotation()
		self._pressed = True
		self._lastTime = QtCore.QTime.currentTime()
		self._lastPos = point
		self._angularVelocity = 0

	def move(self, point, reference) :
		if not self._pressed : return

		currentTime = QtCore.QTime.currentTime()
		msecs = self._lastTime.msecsTo(currentTime)
		if msecs <= 20 : return # ignore frequent

		if True : # Plane method
			delta = QtCore.QLineF(self._lastPos, point)
			self._angularVelocity = 180*delta.length() / (math.pi*msecs)
			self._axis = QtGui.QVector3D(-delta.dy(), delta.dx(), 0.0).normalized()
			self._axis = reference.rotatedVector(self._axis)
			self._rotation = QtGui.QQuaternion.fromAxisAndAngle(self._axis, 180 / math.pi * delta.length()) * self._rotation
		else : # Sphere method
			lastPos3D = QtGui.QVector3D(self._lastPos.x(), self._lastPos.y(), 0.0)
			sqrZ = 1 - QtGui.QVector3D.dotProduct(lastPos3D, lastPos3D)
			if sqrZ > 0 :
				lastPos3D.setZ(math.sqrt(sqrZ))
			else :
				lastPos3D.normalize()

			currentPos3D = QtGui.QVector3D(point.x(), point.y(), 0.0)
			sqrZ = 1 - QtGui.QVector3D.dotProduct(currentPos3D, currentPos3D)
			if sqrZ > 0 :
				currentPos3D.setZ(math.sqrt(sqrZ))
			else :
				currentPos3D.normalize()

			self._axis = QtGui.QVector3D.crossProduct(lastPos3D, currentPos3D)
			angle = 180 / math.pi * math.asin(math.sqrt(QtGui.QVector3D.dotProduct(self._axis, self._axis)))

			self._angularVelocity = angle / msecs
			self._axis.normalize()
			self._axis = reference.rotatedVector(self._axis)
			self._rotation = QtGui.QQuaternion.fromAxisAndAngle(self._axis, angle) * self._rotation



		self._lastTime = currentTime
		self._lastPos = point


	def release(self, point, reference) :
		self.move(point, reference)
		self._pressed = False


class SpherePointScene(QtGui.QGraphicsScene) :

	def __init__(self) :
		super(SpherePointScene, self).__init__()
		self._frame = 0
		self._distance = 600

		self._trackballs = [
			TrackBall(),
			TrackBall(),
			TrackBall(),
			]
		self.startTimer(20)
		self._points = []
		self._vertices = None
		self._indexes = None
		self._normals = None

	def timerEvent(self, event) :
		self.update()

	def setEadPoints(self, points) :
		self._points = points
		self.update()

	def drawBackground(self, painter, rect) :
		height = float(painter.device().height())
		width = float(painter.device().width())

		painter.beginNativePainting()
		self.setStates()

		GL.glClearColor(0.0, 0.0, 0.0, 0.0)
		GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

		GL.glMatrixMode(GL.GL_PROJECTION)
		GLU.gluPerspective(60.0, width / height, 0.01, 150.0);
		GLU.gluLookAt(-20,0,0,0,0,0,0,0,1);

		GL.glMatrixMode(GL.GL_MODELVIEW);

		view = QtGui.QMatrix4x4()
		view.rotate(self._trackballs[2].rotation())
#		view.data().reshape(4,4)[2, 3] -= 2.0 * math.exp(self._distance / 1200.0);
		GL.glLoadMatrixf(view.data())
		self.drawAxis()
#		self.drawPoints()
		self.drawSphere()

		self.setDefaultState()
		painter.endNativePainting()
		++self._frame;

	def drawPoints(self) :
		GL.glEnable(GL.GL_CULL_FACE)
		GL.glEnable(GL.GL_LIGHTING)
		quadric = GLU.gluNewQuadric()
		for e,a,d in self._points :
			ra, re = math.radians(a), math.radians(e)
			sa, se = math.sin(ra), math.sin(re)
			ca, ce = math.cos(ra), math.cos(re)
			if d<0 :
				GL.glColor(1., 1., 1., .5)
				d = -d
			else :
				GL.glColor(1., .6, .6, .5)
			GL.glPushMatrix()
			GL.glTranslate(d*ce*ca, d*ce*sa,d*se)
			GLU.gluSphere(quadric, .1, 10, 10)
			GL.glPopMatrix()

	def drawSphere(self) :
		if self._indexes is None : return

		GL.glDisable(GL.GL_CULL_FACE)
#		GL.glEnable(GL.GL_LIGHTING)
#		GL.glScale(1,1,1)

#		GL.glDisable(GL.GL_LIGHTING)
		GL.glEnableClientState( GL.GL_VERTEX_ARRAY )
		GL.glEnableClientState( GL.GL_COLOR_ARRAY )
		GL.glEnableClientState( GL.GL_NORMAL_ARRAY )

		GL.glColorPointer( 3, GL.GL_FLOAT, 0, self._meshColors)
		GL.glVertexPointer( 3, GL.GL_FLOAT, 0, self._vertices )
		GL.glNormalPointer( GL.GL_FLOAT, 0, self._normals )
#		GL.glDrawElements( GL.GL_TRIANGLE_STRIP, len(self._indexes), GL.GL_UNSIGNED_INT, self._indexes )
		
		GL.glDisableClientState( GL.GL_COLOR_ARRAY )
		GL.glColor(0.6,.3,.6)
		GL.glDrawElements( GL.GL_POINTS, len(self._indexes), GL.GL_UNSIGNED_INT, self._indexes )

		GL.glDisableClientState( GL.GL_COLOR_ARRAY )
		GL.glDisableClientState( GL.GL_VERTEX_ARRAY )
		GL.glDisableClientState( GL.GL_NORMAL_ARRAY )


	def drawAxis(self) :

		GL.glPushAttrib(GL.GL_ENABLE_BIT)
		GL.glDisable(GL.GL_LIGHTING)

		GL.glLineWidth(1)

		GL.glBegin(GL.GL_LINES)

		GL.glColor(0,0,1.)
		GL.glVertex3f(0, 0, -10)
		GL.glVertex3f(0, 0, +10)

		GL.glColor(1.,0,0)
		GL.glVertex3f(-10, 0, 0)
		GL.glVertex3f(+10, 0, 0)

		GL.glColor(0,1.,0)
		GL.glVertex3f(0, -10, 0)
		GL.glVertex3f(0, +10, 0)

		GL.glEnd()

		GL.glPopAttrib()




	def setStates(self) :
		GL.glEnable(GL.GL_DEPTH_TEST)
		GL.glEnable(GL.GL_CULL_FACE)
		GL.glEnable(GL.GL_LIGHTING)
		GL.glEnable(GL.GL_COLOR_MATERIAL)
#		GL.glEnable(GL.GL_TEXTURE_2D)
		GL.glEnable(GL.GL_NORMALIZE)
		GL.glPolygonMode(GL.GL_FRONT, GL.GL_LINE);

		GL.glMatrixMode(GL.GL_PROJECTION)
		GL.glPushMatrix()
		GL.glLoadIdentity()

		GL.glMatrixMode(GL.GL_MODELVIEW)
		GL.glPushMatrix()
		GL.glLoadIdentity()

		self.setLights()

		materialSpecular = [0.2, 0.5, 0.5, 1.0]
		GL.glMaterialfv(GL.GL_FRONT_AND_BACK, GL.GL_SPECULAR, materialSpecular);
		GL.glMaterialf(GL.GL_FRONT_AND_BACK, GL.GL_SHININESS, 32),

	def setDefaultState(self) :
#		GL.glClearColor(0.0, 0.0, 0.0, 0.0)

		GL.glDisable(GL.GL_DEPTH_TEST)
		GL.glDisable(GL.GL_CULL_FACE)
		GL.glDisable(GL.GL_LIGHTING)
#		GL.glDisable(GL.GL_COLOR_MATERIAL)
		GL.glDisable(GL.GL_TEXTURE_2D)
		GL.glDisable(GL.GL_LIGHT0)
		GL.glDisable(GL.GL_NORMALIZE)

		GL.glMatrixMode(GL.GL_MODELVIEW)
		GL.glPopMatrix()

		GL.glMatrixMode(GL.GL_PROJECTION)
		GL.glPopMatrix()

		GL.glLightModelf(GL.GL_LIGHT_MODEL_LOCAL_VIEWER, 0.0)
		defaultMaterialSpecular = [0.0, 0.0, 0.0, 1.0]
		GL.glMaterialfv(GL.GL_FRONT_AND_BACK, GL.GL_SPECULAR, defaultMaterialSpecular)
		GL.glMaterialf(GL.GL_FRONT_AND_BACK, GL.GL_SHININESS, 0.0)

	def setLights(self) :

		GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)
		lightColour = 1.0, 1.0, 0.8, 0.1
		lightDiffuse = .4, .4, 0.4, 1.
		lightDir = 0.0, 1.0, 0.8, 0.0
		GL.glLightfv(GL.GL_LIGHT0, GL.GL_DIFFUSE, lightDiffuse)
		GL.glLightfv(GL.GL_LIGHT0, GL.GL_SPECULAR, lightColour)
		GL.glLightfv(GL.GL_LIGHT0, GL.GL_POSITION, lightDir);
		GL.glLightModelf(GL.GL_LIGHT_MODEL_LOCAL_VIEWER, 1.0)
		GL.glEnable(GL.GL_LIGHT0)

		GL.glLightfv(GL.GL_LIGHT1, GL.GL_DIFFUSE, (.4,.5,.7))
		GL.glLightfv(GL.GL_LIGHT1, GL.GL_SPECULAR, lightColour)
		GL.glLightfv(GL.GL_LIGHT1, GL.GL_POSITION, (-.5,-.2,-.5,0));
		GL.glLightModelf(GL.GL_LIGHT_MODEL_LOCAL_VIEWER, 1.0)
		GL.glEnable(GL.GL_LIGHT1)


	def wheelEvent(self, event) :
		QtGui.QGraphicsScene.wheelEvent(self,event)
		if event.isAccepted() : return

		self._distance += event.delta();
		if self._distance < -8 * 120 : self._distance = -8 * 120
		if self._distance > 10 * 120 : self._distance = 10 * 120
		event.accept()

	def pixelPosToViewPos(self, p) :
		return QtCore.QPointF(
			1.0 - 2.0 * float(p.y()) / self.height(),
			2.0 * float(p.x()) / self.width() - 1.0,
			)

	def mouseMoveEvent(self, event) :
		QtGui.QGraphicsScene.mouseMoveEvent(self, event)
		if event.isAccepted() : return

		mousePos = self.pixelPosToViewPos(event.scenePos())

		if event.buttons() & Qt.LeftButton :
			self._trackballs[0].move(mousePos, self._trackballs[2].rotation().conjugate())
			event.accept()
		else :
			self._trackballs[0].release(mousePos, self._trackballs[2].rotation().conjugate())

		if event.buttons() & Qt.RightButton :
			self._trackballs[1].move(mousePos, self._trackballs[2].rotation().conjugate())
			event.accept()
		else :
			self._trackballs[1].release(mousePos, self._trackballs[2].rotation().conjugate());


		if event.buttons() & Qt.MidButton :
			self._trackballs[2].move(mousePos, QtGui.QQuaternion())
			event.accept();
		else :
			self._trackballs[2].release(mousePos, QtGui.QQuaternion())



	def mousePressEvent(self, event) :
		QtGui.QGraphicsScene.mousePressEvent(self, event)
		if event.isAccepted() : return

		mousePos = self.pixelPosToViewPos(event.scenePos())

		if event.buttons() & Qt.LeftButton :
			self._trackballs[0].push(mousePos, self._trackballs[2].rotation().conjugate())
			event.accept()

		if event.buttons() & Qt.RightButton :
			self._trackballs[1].push(mousePos, self._trackballs[2].rotation().conjugate())
			event.accept()

		if event.buttons() & Qt.MidButton :
			self._trackballs[2].push(mousePos, QtGui.QQuaternion())
			event.accept();


	def mouseReleaseEvent(self, event) :
		QtGui.QGraphicsScene.mouseReleaseEvent(self, event)
		if event.isAccepted() : return

		mousePos = self.pixelPosToViewPos(event.scenePos())

		if event.buttons() & Qt.LeftButton :
			self._trackballs[0].release(mousePos, self._trackballs[2].rotation().conjugate())
			event.accept()

		if event.buttons() & Qt.RightButton :
			self._trackballs[1].release(mousePos, self._trackballs[2].rotation().conjugate())
			event.accept()

		if event.buttons() & Qt.MidButton :
			self._trackballs[2].release(mousePos, QtGui.QQuaternion())
			event.accept();




class SpherePointView(QtGui.QGraphicsView) :

	def __init__(self) :
		super(SpherePointView, self).__init__()
		self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
#		self.setRenderHints(QtGui.QPainter.SmoothPixmapTransform)
		viewPort = QtOpenGL.QGLWidget()
		self.setViewport(viewPort)
		self.setViewportUpdateMode(QtGui.QGraphicsView.FullViewportUpdate);
		scene = SpherePointScene()
		self.setScene(scene);


	def resizeEvent(self, event) :
		if self.scene() :
			self.scene().setSceneRect(QtCore.QRect(QtCore.QPoint(0, 0), event.size()))
		super(SpherePointView, self).resizeEvent(event)

	def setEadPoints(self, points) :
		self.scene().setEadPoints( points)


class SphericalHarmonicsControl(QtGui.QWidget) :

	def __init__(self) :
		def addSpin(name, minimum, default, maximum, slot) :
			topLayout.addWidget(QtGui.QLabel(name+":"))
			spin = QtGui.QSpinBox()
			spin.setMinimum(minimum)
			spin.setMaximum(maximum)
			spin.setValue(default)
			spin.valueChanged.connect(slot)
			topLayout.addWidget(spin)
			return spin
			
		QtGui.QWidget.__init__(self)
		self.setLayout(QtGui.QVBoxLayout())
		self._grid = QtGui.QGridLayout()
		topLayout = QtGui.QHBoxLayout()
		self._orderSpin = addSpin("Order", 0, 5, 10, self.orderChanged)
		topLayout.addStretch(1)
		self._parallelsSpin = addSpin("Parallels", 4, 50, 400, self.resolutionChanged)
		topLayout.addStretch(1)
		self._meridiansSpin = addSpin("Meridians", 4, 50, 400, self.resolutionChanged)
		resetButton = QtGui.QPushButton("Reset")
		resetButton.clicked.connect(self.reset)
		topLayout.addWidget(resetButton)
		self.layout().addLayout(topLayout)
		self.layout().addLayout(self._grid)


		def componentKnob(i,j) :
			l = max(i,j)
			m = i-j
			knob = QtGui.QDial()
			knob.setMinimum(-100)
			knob.setMaximum(+100)
			knob.setStyleSheet("background-color: %s"%orderColors[l%len(orderColors)])
			label = QtGui.QLabel("%d,%+d"%(l,m))
			label.setAlignment(Qt.AlignCenter)
			self._grid.addWidget(label, i*2, j)
			self._grid.addWidget(knob, i*2+1, j)
			knob.valueChanged.connect(self.functionChanged)
			return knob

		order = 5
		orderColors = [
			"#889988",
			"#667766",
			"#bb7788",
			"#aa6666",
			]
		self._knobs = [[
			componentKnob(i,j)
			for j in xrange(order+1) ]
			for i in xrange(order+1) ]

	functionChanged = QtCore.Signal()
	resolutionChanged = QtCore.Signal()

	def orderChanged(self) :
		order = self._orderSpin.value()

	def sphericalHarmonicsMatrix(self) :
		return np.array([[
			knob.value()/100.
			for knob in row ]
			for row in self._knobs ])

	def reset(self) :
		for row in self._knobs :
			for knob in row:
				knob.setValue(0)



if __name__ == "__main__" :

	width = 800
	height = 600

	app = QtGui.QApplication(sys.argv)

	w = QtGui.QDialog()
	w.setLayout(QtGui.QHBoxLayout())

	w0 = SphericalHarmonicsControl()
	w.layout().addWidget(w0)

	leftLayout = QtGui.QVBoxLayout()
	w.layout().addLayout(leftLayout)
	
	w2 = SpherePointView()
	leftLayout.addWidget(w2)

	w1 = ColorField(width, height)
#	reloader1 = Reloader(w1)
#	reloader1.startTimer(0)
	leftLayout.addWidget(w1)

	leftLayout.setStretch(0,3)
	leftLayout.setStretch(1,1)
	w.layout().setStretch(0,1)
	w.layout().setStretch(1,1)

	w.resize(width, height)



	def sh(sh, e, a) :
		x,y,z = ead2xyz(e, a, 1)
		return 5*math.sqrt(1/math.pi)*(
			math.sqrt(1./2) * (
				sh[0,0] +
				0
			) +
			math.sqrt(1./4) * (
				sh[0,1] * x +
				sh[1,1] * z +
				sh[1,0] * y +
				0
			) +
			math.sqrt(15./16) * (
				sh[2,0] * (x*y) +
				sh[2,1] * (x*z) +
				sh[2,2] * (2*z*z -x*x -y*y) * math.sqrt(1./3) +
				sh[1,2] * (y*z) +
				sh[0,2] * (x*x -y*y) +
				0
			) +
			(
				sh[3,0] * x*(x*x-3*y*y)           * math.sqrt(35./32) +
				sh[3,1] * z*x*y                   * math.sqrt(105./4)+
				sh[3,2] * x*(4*z*z -x*x -y*y)     * math.sqrt(21./32) +
				sh[3,3] * z*(2*z*z -3*x*x -3*y*y) * math.sqrt(7./16) +
				sh[2,3] * y*(4*z*z -x*x -y*y)     * math.sqrt(21./32) +
				sh[1,3] * z*(x*x-y*y)             * math.sqrt(105./16) +
				sh[0,3] * y*(3*x*x-y*y)           * math.sqrt(35./32) +
				0
				)
			)

	def reloadData() :
		nelevations = w0._parallelsSpin.value()
		nazimuths = w0._meridiansSpin.value()
		elevations = np.linspace(  -90,  90, nelevations)
		azimuths = np.linspace( -180, 180, nazimuths, endpoint=False)
		shMatrix = w0.sphericalHarmonicsMatrix()
		data = np.array([[
			sh(shMatrix, e, a)
			for a in azimuths ]
			for e in elevations ]
			)

		sphericalPoints = [
			(e, a, sh(shMatrix, e, a) )
			for e,a in cartesian_product(elevations, azimuths)]
		w2.setEadPoints(sphericalPoints)
		w2.scene()._vertices = np.array([ead2xyz(e,a,abs(d)) for e,a,d in sphericalPoints])
		w2.scene()._normals = np.array([ead2xyz(e,a,abs(d)) for e,a,d in sphericalPoints])
		w2.scene()._meshColors = np.array([[1.,.0,.0] if d<0 else [0.,0.,1.] for e,a,d in sphericalPoints])
		w2.scene()._indexes = np.array(
			[[
				[i+nazimuths*j,i+nazimuths*(j+1)]
				for i in xrange(nazimuths) ]
				for j in xrange(nelevations-1) ]
			).flatten()
		w2.update()
		w1.format(nazimuths, nelevations, ColorField.signedScale)
		w1.data()[:] = data/(10/255.)+127
#		w1.data()[:,0] =127 # azimuth
#		w1.data()[:,-1] =127 # azimuth
		w1.data()[0,:] =127 # elevation
		w1.data()[-1,:] =127 # elevation
		print w1.data()
		w1.reload()

	w0.resolutionChanged.connect(reloadData)
	w0.functionChanged.connect(reloadData)

	reloadData()

	w.show()

	app.exec_()



