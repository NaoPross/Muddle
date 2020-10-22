#
# This document *and this document only* uses the Qt naming convention instead
# of PEP because the PyQt5 bindings do not have pythonic names
#

import sys
import json
import enum
import html
import logging

from PyQt5.QtGui import QFont
from PyQt5.Qt import QStyle
from PyQt5.QtCore import Qt, QThread, pyqtSlot, pyqtSignal, QObject
from PyQt5.QtWidgets import QApplication, QWidget, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QGridLayout, QHBoxLayout, QPushButton, QProgressBar, QTabWidget, QPlainTextEdit

import moodle

log = logging.getLogger("muddle.gui")

class MoodleItem(QTreeWidgetItem):
    class Type(enum.IntEnum):
        ROOT       = 0
        # root
        COURSE     = 1
        # sections
        SECTION    = 2
        # modules
        MODULE     = 3
        ## specific module types
        FORUM      = 4
        RESOURCE   = 5
        FOLDER     = 6
        ATTENDANCE = 7
        LABEL      = 8
        QUIZ       = 9
        # contents
        CONTENT    = 10
        ## specific content types
        FILE       = 11
        URL        = 12

    class Metadata:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    def __init__(self, parent, nodetype, leaves=[], **kwargs):
        super().__init__(parent)
        self.metadata = MoodleItem.Metadata(type = nodetype, **kwargs)
        self.setupQt()

    def setupQt(self):
        font = QFont("Monospace")
        font.setStyleHint(QFont.Monospace)
        self.setFont(0, font)

        icons = {
            MoodleItem.Type.COURSE   : QStyle.SP_DriveNetIcon,
            MoodleItem.Type.FOLDER   : QStyle.SP_DirIcon,
            MoodleItem.Type.RESOURCE : QStyle.SP_DirLinkIcon,
            MoodleItem.Type.FILE     : QStyle.SP_FileIcon,
            MoodleItem.Type.URL      : QStyle.SP_FileLinkIcon,
        }

        if icons.get(self.metadata.type):
            self.setIcon(0, QApplication.style().standardIcon(icons[self.metadata.type]))

        flags = self.flags()
        if self.metadata.type in [ MoodleItem.Type.FILE, MoodleItem.Type.FOLDER, MoodleItem.Type.RESOURCE ]:
            self.setFlags(flags | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            self.setCheckState(0, Qt.Unchecked)
        else:
            self.setFlags(flags & ~Qt.ItemIsUserCheckable)

        self.setChildIndicatorPolicy(QTreeWidgetItem.DontShowIndicatorWhenChildless)
        self.setText(0, html.unescape(self.metadata.title))

class MoodleFetcher(QThread):
    loadedItem = pyqtSignal(MoodleItem.Type, object)

    def __init__(self, parent, instance_url, token):
        super().__init__()

        self.api = moodle.RestApi(instance_url, token)
        self.apihelper = moodle.ApiHelper(self.api)

    def run(self):
        # This is beyond bad but I don't have access to the moodle documentation, so I had to guess
        for course in self.getCourses():
            self.loadedItem.emit(MoodleItem.Type.COURSE, course)
            for section in self.getSections(course):
                self.loadedItem.emit(MoodleItem.Type.SECTION, section)
                for module in self.getModules(section):
                    self.loadedItem.emit(MoodleItem.Type.MODULE, module)
                    for content in self.getContent(module):
                        self.loadedItem.emit(MoodleItem.Type.CONTENT, content)

    def getCourses(self):
        coursesReq = self.api.core_enrol_get_users_courses(userid = self.apihelper.get_userid())
        if not coursesReq:
            return []

        return coursesReq.json()

    def getSections(self, course):
        if not "id" in course:
            log.error("cannot get sections from invalid course (no id)")
            log.debug(course)
            return []

        sectionsReq = self.api.core_course_get_contents(courseid = str(course["id"]))
        if not sectionsReq:
            return []

        sections = sectionsReq.json()
        return sections

    def getModules(self, section):
        if "modules" in section:
            return section["modules"]
        else:
            return []

    def getContent(self, module):
        if "contents" in module:
            return module["contents"]
        else:
            return []

class MoodleTreeView(QTreeWidget):
    def __init__(self, parent, instance_url, token):
        super().__init__(parent)

        self.lastInsertedItem = None

        self.initUi()

        self.worker = MoodleFetcher(self, instance_url, token)
        self.worker.loadedItem.connect(self.onWorkerLoadedItem)
        self.worker.finished.connect(self.onWorkerDone)
        self.worker.start()

        self.show()

    def initUi(self):
        self.setHeaderHidden(True)
        self.itemDoubleClicked.connect(self.onItemDoubleClicked, Qt.QueuedConnection)

    @pyqtSlot(QTreeWidgetItem, int)
    def onItemDoubleClicked(self, item, col):
        log.debug(f"double clicked on item with type {str(item.metadata.type)}")
        if item.metadata.type == MoodleItem.Type.FILE:
            # TODO: download in a temp folder and open
            pass

    @pyqtSlot(MoodleItem.Type, object)
    def onWorkerLoadedItem(self, type, item):
        # Assume that the items arrive in order
        moodleItem = None
        parent = None

        if type == MoodleItem.Type.COURSE:
            moodleItem = MoodleItem(parent = parent, nodetype = type, id = item["id"], title = item["shortname"])
            self.addTopLevelItem(moodleItem)
        else:
            parent = self.lastInsertedItem
            while type <= parent.metadata.type and parent.parent():
                parent = parent.parent()

        if type == MoodleItem.Type.SECTION:
            moodleItem = MoodleItem(parent = parent, nodetype = type, id = item["id"], title = item["name"])
        elif type == MoodleItem.Type.MODULE:
            moduleType = {
                "folder"     : MoodleItem.Type.FOLDER,
                "resource"   : MoodleItem.Type.RESOURCE,
                "forum"      : MoodleItem.Type.FORUM,
                "attendance" : MoodleItem.Type.ATTENDANCE,
                "label"      : MoodleItem.Type.LABEL,
                "quiz"       : MoodleItem.Type.QUIZ,
            }

            moodleItem = MoodleItem(parent = parent, nodetype = moduleType.get(item["modname"]) or type, id = item["id"], title = item["name"])
        elif type == MoodleItem.Type.CONTENT:
            contentType = {
                "url" : MoodleItem.Type.URL,
                "file" : MoodleItem.Type.FILE,
            }
            moodleItem = MoodleItem(parent = parent, nodetype = contentType.get(item["type"]) or type, title = item["filename"], url = item["fileurl"])

        if not moodleItem:
            log.error(f"Could not load item of type {type}")
            return

        self.lastInsertedItem = moodleItem

    @pyqtSlot()
    def onWorkerDone(self):
        log.debug("worker done")
        self.sortByColumn(0, Qt.AscendingOrder)
        self.setSortingEnabled(True)

class QLogHandler(QObject, logging.Handler):
    newLogMessage = pyqtSignal(str)

    def emit(self, record):
        msg = self.format(record)
        self.newLogMessage.emit(msg)

    def write(self, m):
        pass

class Muddle(QTabWidget):
    def __init__(self, instance_url, token):
        super().__init__()
        self.instance_url = instance_url
        self.token = token
        self.initUi()

    def initUi(self):
        self.setWindowTitle("Muddle")

        # moodle tab
        self.tabmoodle = QWidget()
        self.addTab(self.tabmoodle, "Moodle")

        self.tabmoodle.setLayout(QGridLayout())
        self.tabmoodle.layout().addWidget(MoodleTreeView(self, self.instance_url, self.token), 0, 0, 1, -1)

        # TODO: make number of selected element appear
        # TODO: add path selector, to select where to download the files
        self.tabmoodle.downloadbtn = QPushButton("Download")
        self.tabmoodle.selectallbtn = QPushButton("Select All")
        self.tabmoodle.deselectallbtn = QPushButton("Deselect All")
        self.tabmoodle.progressbar = QProgressBar()

        self.tabmoodle.layout().addWidget(self.tabmoodle.downloadbtn, 1, 0)
        self.tabmoodle.layout().addWidget(self.tabmoodle.selectallbtn, 1, 1)
        self.tabmoodle.layout().addWidget(self.tabmoodle.deselectallbtn, 1, 2)
        self.tabmoodle.layout().addWidget(self.tabmoodle.progressbar, 2, 0, 1, -1)

        # log tabs
        self.loghandler = QLogHandler(self)
        self.loghandler.setFormatter(logging.Formatter("%(name)s - %(levelname)s - %(message)s"))
        self.loghandler.newLogMessage.connect(self.onNewLogMessage)
        logging.getLogger("muddle").addHandler(self.loghandler)

        font = QFont("Monospace")
        font.setStyleHint(QFont.Monospace)

        self.logtext = QPlainTextEdit()
        self.logtext.setReadOnly(True)
        self.logtext.setFont(font)

        self.addTab(self.logtext, "Logs")

        self.show()

    @pyqtSlot(str)
    def onNewLogMessage(self, msg):
        self.logtext.appendPlainText(msg)


def start(instance_url, token):
    app = QApplication(sys.argv)
    ex = Muddle(instance_url, token)
    sys.exit(app.exec_())
