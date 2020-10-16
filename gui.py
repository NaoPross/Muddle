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
from PyQt5.QtCore import Qt, QThread, pyqtSlot
from PyQt5.QtWidgets import QApplication, QWidget, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QGridLayout, QHBoxLayout, QPushButton, QProgressBar, QTabWidget, QPlainTextEdit

import moodle

log = logging.getLogger("muddle.gui")

class MoodleItem(QTreeWidgetItem):
    class Type(enum.Enum):
        ROOT       = 0
        # root
        COURSE     = 1
        # sections
        SECTION    = 2
        # modules
        MODULE     = 3
        FORUM      = 4
        RESOURCE   = 5
        FOLDER     = 6
        ATTENDANCE = 7
        LABEL      = 8
        QUIZ       = 9
        # contents
        CONTENT    = 10
        FILE       = 11
        URL        = 12

    class Metadata:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    def __init__(self, nodetype, leaves=[], **kwargs):
        super().__init__()
        self.metadata = MoodleItem.Metadata(type = nodetype, **kwargs)
        self.setupQt()

    # TODO: Qt objects should be on the main thread
    # prob cause of the crash
    def setupQt(self):
        font = QFont("Monospace")
        font.setStyleHint(QFont.Monospace)
        self.setFont(0, font)

        icons = {
            MoodleItem.Type.COURSE   : QApplication.style().standardIcon(QStyle.SP_DriveNetIcon),
            MoodleItem.Type.FOLDER   : QApplication.style().standardIcon(QStyle.SP_DirIcon),
            MoodleItem.Type.FILE     : QApplication.style().standardIcon(QStyle.SP_FileIcon),
            MoodleItem.Type.URL      : QApplication.style().standardIcon(QStyle.SP_FileLinkIcon),
        }

        if icons.get(self.type):
            self.setIcon(0, icons[self.metadata.type])

        if self.metadata.type == MoodleItem.Type.FILE:
            flags = self.flags()
            self.setFlags(flags | Qt.ItemIsUserCheckable)
            self.setCheckState(0, Qt.Unchecked)

        self.setChildIndicatorPolicy(QTreeWidgetItem.DontShowIndicatorWhenChildless)
        self.setText(0, html.unescape(self.metadata.title))

class MoodleFetcher(QThread):
    def __init__(self, parent, instance_url, token):
        super().__init__()

        self.api = moodle.RestApi(instance_url, token)
        self.apihelper = moodle.ApiHelper(self.api)
        self.moodleItems = MoodleItem(MoodleItem.Type.ROOT, title="ROOT")

    def run(self):
        # This is beyond bad but I don't have access to the moodle documentation, so I had to guess
        courses = self.api.core_enrol_get_users_courses(userid=self.apihelper.get_userid()).json()
        for course in courses:
            courseItem = MoodleItem(MoodleItem.Type.COURSE, 
                    id = course["id"], title = course["shortname"])

            self.moodleItems.addChild(courseItem)

            sections = self.api.core_course_get_contents(courseid=courseItem.metadata.id).json()

            for section in sections:
                sectionItem = MoodleItem(MoodleItem.Type.SECTION,
                        id = section["id"], title = section["name"])

                courseItem.addChild(sectionItem)

                modules = section["modules"] if "modules" in section else []
                for module in modules:
                    moduleType = {
                        "folder"     : MoodleItem.Type.FOLDER,
                        "resource"   : MoodleItem.Type.RESOURCE,
                        "forum"      : MoodleItem.Type.FORUM,
                        "attendance" : MoodleItem.Type.ATTENDANCE,
                        "label"      : MoodleItem.Type.LABEL,
                        "quiz"       : MoodleItem.Type.QUIZ,
                    }

                    moduleItem = MoodleItem(moduleType.get(module["modname"]) or MoodleItem.Type.MODULE,
                            id = module["id"], title = module["name"])

                    sectionItem.addChild(moduleItem)

                    contents = module["contents"] if "contents" in module else []
                    for content in contents:
                        contentType = {
                            "url" : MoodleItem.Type.URL,
                            "file" : MoodleItem.Type.FILE,
                        }

                        contentItem = MoodleItem(contentType.get(content["type"]) or MoodleItem.Type.MODULE,
                                title = content["filename"], url = content["fileurl"])

                        moduleItem.addChild(contentItem)


class MoodleTreeView(QTreeWidget):
    def __init__(self, parent, instance_url, token):
        super().__init__(parent)

        self.worker = MoodleFetcher(self, instance_url, token)
        self.worker.finished.connect(self.onWorkerDone)
        self.worker.start()

        self.initUi()
        self.show()

    def initUi(self):
        self.setHeaderHidden(True)
        self.itemDoubleClicked.connect(self.onItemDoubleClicked, Qt.QueuedConnection)

    @pyqtSlot(QTreeWidgetItem, int)
    def onItemDoubleClicked(self, item, col):
        log.debug(f"double clicked on item with type {str(item.type)}")
        if item.type == MoodleItem.Type.FILE:
            pass

    @pyqtSlot()
    def onWorkerDone(self):
        log.debug("worker done")
        for item in QTreeWidgetItemIterator(self.worker.moodleItems):
            self.addTopLevelItem(item)

        # sort only after the worker is done for efficiency
        self.setSortingEnabled(True)

class QPlainTextEditLogger(logging.Handler):
    def __init__(self, parent):
        super().__init__()
        # TODO: set monospaced font
        self.widget = QPlainTextEdit(parent)
        self.widget.setReadOnly(True)

    def emit(self, record):
        msg = self.format(record)
        self.widget.appendPlainText(msg)

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
        handler = QPlainTextEditLogger(self)
        handler.setFormatter(logging.Formatter("%(name)s - %(levelname)s - %(message)s"))
        logging.getLogger("muddle").addHandler(handler)

        self.tablogs = handler.widget
        self.addTab(self.tablogs, "Logs")

        self.show()


def start(instance_url, token):
    app = QApplication(sys.argv)
    ex = Muddle(instance_url, token)
    sys.exit(app.exec_())
