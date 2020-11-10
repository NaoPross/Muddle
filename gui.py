#
# This document *and this document only* uses the Qt naming convention instead
# of PEP because the PyQt5 bindings do not have pythonic names
#
import os
import platform
import subprocess
import sys
import json
import enum
import html
import logging
import tempfile

from PyQt5 import uic
from PyQt5.QtGui import QFont, QIcon, QStandardItemModel, QStandardItem
from PyQt5.Qt import QStyle

from PyQt5.QtCore import (
    Qt,
    QDir,
    QThread,
    pyqtSlot,
    pyqtSignal,
    QObject,
    QRegularExpression,
    QSortFilterProxyModel,
)

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QTreeView,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QHeaderView,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QToolButton,
    QLineEdit,
    QProgressBar,
    QTabWidget,
    QPlainTextEdit,
    QFileSystemModel,
    QFileDialog,
)

import moodle

log = logging.getLogger("muddle.gui")

class MoodleItem(QStandardItem):
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

        # set icon
        icons = {
            MoodleItem.Type.COURSE   : QStyle.SP_DriveNetIcon,
            MoodleItem.Type.FOLDER   : QStyle.SP_DirIcon,
            MoodleItem.Type.RESOURCE : QStyle.SP_DirLinkIcon,
            MoodleItem.Type.FILE     : QStyle.SP_FileIcon,
            MoodleItem.Type.URL      : QStyle.SP_FileLinkIcon,
        }

        if self.metadata.type in icons.keys():
            self.setIcon(QApplication.style().standardIcon(icons[self.metadata.type]))
        else:
            # remove icon, because otherwise it inherits the parent's icon
            self.setIcon(QIcon())

        if self.metadata.type in [ MoodleItem.Type.FILE, MoodleItem.Type.FOLDER, MoodleItem.Type.RESOURCE ]:
            self.setCheckable(True)
            self.setCheckState(Qt.Unchecked)

        self.setEditable(False)
        self.setText(html.unescape(self.metadata.title))


class MoodleFetcher(QThread):
    loadedItem = pyqtSignal(MoodleItem.Type, object)

    def __init__(self, parent, instance_url, token):
        super().__init__()

        self.api = moodle.RestApi(instance_url, token)
        self.apihelper = moodle.ApiHelper(self.api)

    def run(self):
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


class MoodleTreeFilterModel(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()


class MoodleTreeModel(QStandardItemModel):
    def __init__(self):
        super().__init__()

        self.setHorizontalHeaderLabels(["Item", "Size"])
        self.lastInsertedItem = None
        self.worker = None

    @pyqtSlot(str, str)
    def refresh(self, instance_url, token):
        if not self.worker or self.worker.isFinished():
            self.setRowCount(0) # instead of clear(), because clear() removes the headers

            self.worker = MoodleFetcher(self, instance_url, token)
            self.worker.loadedItem.connect(self.onWorkerLoadedItem)
            self.worker.finished.connect(self.onWorkerDone)
            self.worker.start()
        else:
            log.debug("A worker is already running, not refreshing")

    @pyqtSlot(MoodleItem.Type, object)
    def onWorkerLoadedItem(self, type, item):
        # Assume that the items arrive in order
        moodleItem = None
        parent = None

        # if top level
        if type == MoodleItem.Type.COURSE:
            moodleItem = MoodleItem(
                parent = parent,
                nodetype = type,
                id = item["id"],
                title = item["shortname"])

            self.invisibleRootItem().insertRow(0, moodleItem)
            self.lastInsertedItem = moodleItem

            return

        # otherwise
        parent = self.lastInsertedItem
        while type <= parent.metadata.type and parent.parent():
            parent = parent.parent()

        if type == MoodleItem.Type.SECTION:
            moodleItem = MoodleItem(
                parent = parent,
                nodetype = type,
                id = item["id"],
                title = item["name"])

        elif type == MoodleItem.Type.MODULE:
            moduleType = {
                "folder"     : MoodleItem.Type.FOLDER,
                "resource"   : MoodleItem.Type.RESOURCE,
                "forum"      : MoodleItem.Type.FORUM,
                "attendance" : MoodleItem.Type.ATTENDANCE,
                "label"      : MoodleItem.Type.LABEL,
                "quiz"       : MoodleItem.Type.QUIZ,
            }

            moodleItem = MoodleItem(
                parent = parent,
                nodetype = moduleType.get(item["modname"]) or type,
                id = item["id"],
                title = item["name"])

        elif type == MoodleItem.Type.CONTENT:
            contentType = {
                "url" : MoodleItem.Type.URL,
                "file" : MoodleItem.Type.FILE,
            }

            moodleItem = MoodleItem(
                parent = parent,
                nodetype = contentType.get(item["type"]) or type,
                title = item["filename"],
                url = item["fileurl"])

        if not moodleItem:
            log.error(f"Could not load item of type {type}")
            return

        parent.insertRow(0, moodleItem)
        self.lastInsertedItem = moodleItem
        log.debug(f"inserted item of type {moodleItem.metadata.type}")

    @pyqtSlot()
    def onWorkerDone(self):
        log.debug("worker done")


class QLogHandler(QObject, logging.Handler):
    newLogMessage = pyqtSignal(str)

    def emit(self, record):
        msg = self.format(record)
        self.newLogMessage.emit(msg)

    def write(self, m):
        pass


class MuddleWindow(QMainWindow):
    def __init__(self, instance_url, token):
        super(MuddleWindow, self).__init__()
        uic.loadUi("muddle.ui", self)
        self.setCentralWidget(self.findChild(QTabWidget, "Muddle"))

        # setup logging
        self.loghandler = QLogHandler(self)
        self.loghandler.setFormatter(logging.Formatter("%(name)s - %(levelname)s - %(message)s"))
        self.loghandler.newLogMessage.connect(self.onNewLogMessage)
        logging.getLogger("muddle").addHandler(self.loghandler)

        # set up proxymodel for moodle treeview
        self.moodleTreeModel = MoodleTreeModel()
        self.filterModel = MoodleTreeFilterModel()

        self.filterModel.setRecursiveFilteringEnabled(True)
        self.filterModel.setDynamicSortFilter(True)

        moodleTreeView = self.findChild(QTreeView, "moodleTree")
        self.filterModel.setSourceModel(self.moodleTreeModel)
        moodleTreeView.setModel(self.filterModel)
        moodleTreeView.setSortingEnabled(True)
        moodleTreeView.sortByColumn(0, Qt.AscendingOrder)
        # TODO: change with minimumSize (?)
        moodleTreeView.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)

        # refresh moodle treeview
        refreshBtn = self.findChild(QToolButton, "refreshBtn")
        refreshBtn.clicked.connect(lambda b: self.moodleTreeModel.refresh(instance_url, token))

        # searchbar
        searchBar = self.findChild(QLineEdit, "searchBar")
        searchBar.textChanged.connect(self.onSearchBarTextChanged)
        searchBar.textEdited.connect(self.onSearchBarTextChanged)

        # local filesystem view
        self.downloadPath = QDir.homePath()

        self.fileSystemModel = QFileSystemModel()
        self.fileSystemModel.setRootPath(QDir.homePath())

        localTreeView = self.findChild(QTreeView, "localTab")
        localTreeView.setModel(self.fileSystemModel)
        localTreeView.setRootIndex(self.fileSystemModel.index(QDir.homePath()))
        localTreeView.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)

        downloadPathEdit = self.findChild(QLineEdit, "downloadPathEdit")
        downloadPathEdit.setText(self.downloadPath)
        downloadPathEdit.editingFinished.connect(self.onDownloadPathEditEditingFinished)

        # select path
        selectPathBtn = self.findChild(QToolButton, "selectPathBtn")
        selectPathBtn.clicked.connect(self.onSelectPathBtnClicked)

        self.show()

    @pyqtSlot(str)
    def onSearchBarTextChanged(self, text):
        moodleTreeView = self.findChild(QTreeView, "moodleTree")
        if not text:
            self.filterModel.setFilterRegularExpression(".*")
            moodleTreeView.collapseAll()
        else:
            regexp = QRegularExpression(text)
            if regexp.isValid():
                self.filterModel.setFilterRegularExpression(regexp)
                moodleTreeView.expandAll()
            else:
                log.debug("invalid search regular expression, not searching")

    @pyqtSlot(str)
    def onNewLogMessage(self, msg):
        self.findChild(QPlainTextEdit, "logsTab").appendPlainText(msg)

    @pyqtSlot()
    def onDownloadPathEditEditingFinished(self):
        downloadPathEdit = self.findChild(QLineEdit, "downloadPathEdit")
        path = downloadPathEdit.text()

        if not self.updateDownloadPath(path):
            downloadPathEdit.setText(self.downloadPath)

    @pyqtSlot()
    def onSelectPathBtnClicked(self):
        path = QFileDialog.getExistingDirectory(
                self, "Select Download Directory",
                self.downloadPath, QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks)

        if not path:
            return

        self.updateDownloadPath(path)

    @pyqtSlot()
    def updateDownloadPath(self, newpath):
        if not self.fileSystemModel.index(newpath).isValid():
            return False

        self.downloadPath = newpath

        downloadPathEdit = self.findChild(QLineEdit, "downloadPathEdit")
        localTreeView = self.findChild(QTreeView, "localTab")

        downloadPathEdit.setText(self.downloadPath)
        localTreeView.setRootIndex(self.fileSystemModel.index(self.downloadPath))


def start(instance_url, token):
    app = QApplication(sys.argv)
    ex = MuddleWindow(instance_url, token)
    sys.exit(app.exec_())
