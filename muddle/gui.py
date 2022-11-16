#
# This document *and this document only* uses the Qt naming convention instead
# of PEP because the PyQt6 bindings do not have pythonic names.
#
# See the link below for the official documentation of PyQt6:
#
#   https://www.riverbankcomputing.com/static/Docs/PyQt6/index.html
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

from PyQt6 import uic
from PyQt6.QtGui import (
    QFileSystemModel,
    QFont,
    QIcon,
    QStandardItem,
    QStandardItemModel,
)


from PyQt6.QtCore import (
    QDir,
    QModelIndex,
    QObject,
    QRegularExpression,
    QSignalBlocker,
    QSortFilterProxyModel,
    QThread,
    Qt,
    pyqtSignal,
    pyqtSlot,
)

from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStyle,
    QTabWidget,
    QTreeView,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QWidget,
)

from . import moodle

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
            MoodleItem.Type.COURSE   : QStyle.StandardPixmap.SP_DriveNetIcon,
            MoodleItem.Type.FOLDER   : QStyle.StandardPixmap.SP_DirIcon,
            MoodleItem.Type.RESOURCE : QStyle.StandardPixmap.SP_DirLinkIcon,
            MoodleItem.Type.FILE     : QStyle.StandardPixmap.SP_FileIcon,
            MoodleItem.Type.URL      : QStyle.StandardPixmap.SP_FileLinkIcon,
        }

        if self.metadata.type in icons.keys():
            self.setIcon(QApplication.style().standardIcon(icons[self.metadata.type]))
        else:
            # remove icon, because otherwise it inherits the parent's icon
            self.setIcon(QIcon())

        if self.metadata.type in [ MoodleItem.Type.FILE, MoodleItem.Type.FOLDER, MoodleItem.Type.RESOURCE ]:
            # NOTE: because of a Qt Bug setAutoTristate does not work
            # the tri-state behavior is implemented below in
            # MuddleWindow.onMoodleTreeModelDataChanged()
            self.setCheckable(True)
            self.setCheckState(Qt.CheckState.Unchecked)

        self.setEditable(False)
        self.setText(html.unescape(self.metadata.title))


class MoodleFetcher(QThread):
    loadedItem = pyqtSignal(MoodleItem.Type, object)

    def __init__(self, parent, instanceUrl, token):
        super().__init__()

        self.api = moodle.RestApi(instanceUrl, token)
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
    def refresh(self, instanceUrl, token):
        if not self.worker or self.worker.isFinished():
            self.setRowCount(0) # instead of clear(), because clear() removes the headers

            self.worker = MoodleFetcher(self, instanceUrl, token)
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
    def __init__(self, config):
        super(MuddleWindow, self).__init__()
        uic.loadUi("muddle/muddle.ui", self)
        self.setCentralWidget(self.findChild(QTabWidget, "Muddle"))

        self.instanceUrl = config["server"]["url"] if config.has_option("server", "url") else None
        self.token = config["server"]["token"] if config.has_option("server", "token") else None

        # config tab
        ## TODO: when any of the settings change, update the values (but not in the config, yet)

        instanceUrlEdit = self.findChild(QLineEdit, "instanceUrlEdit")
        if self.instanceUrl:
            instanceUrlEdit.setText(self.instanceUrl)

        tokenEdit = self.findChild(QLineEdit, "tokenEdit")
        if self.token:
            tokenEdit.setText(self.token)

        requestTokenBtn = self.findChild(QPushButton, "requestTokenBtn")
        requestTokenBtn.clicked.connect(self.onRequestTokenBtnClicked)

        tokenEdit.textEdited.connect(lambda text: requestTokenBtn.setEnabled(not bool(text)))

        alwaysStartGuiCheckBox = self.findChild(QCheckBox, "alwaysStartGuiCheckBox")
        if config.has_option("muddle", "always_run_gui"):
            alwaysStartGuiCheckBox.setChecked(config.getboolean("muddle", "always_run_gui"))

        configEdit = self.findChild(QLineEdit, "configEdit")
        configEdit.setText(config["runtime_data"]["config_path"])

        defaultDownloadPathEdit = self.findChild(QLineEdit, "defaultDownloadPathEdit")
        if config.has_option("muddle", "default_download_dir"):
            defaultDownloadPathEdit.setText(config["muddle"]["default_download_dir"])


        # log tab
        ## setup logging
        self.loghandler = QLogHandler(self)
        self.loghandler.setFormatter(logging.Formatter("%(name)s - %(levelname)s - %(message)s"))
        self.loghandler.newLogMessage.connect(self.onNewLogMessage)
        logging.getLogger("muddle").addHandler(self.loghandler)

        # moodle tab
        ## set up proxymodel for moodle treeview
        self.moodleTreeModel = MoodleTreeModel()
        self.moodleTreeModel.dataChanged.connect(self.onMoodleTreeModelDataChanged)

        self.filterModel = MoodleTreeFilterModel()
        self.filterModel.setRecursiveFilteringEnabled(True)
        self.filterModel.setDynamicSortFilter(True)
        self.filterModel.setSourceModel(self.moodleTreeModel)

        moodleTreeView = self.findChild(QTreeView, "moodleTree")
        moodleTreeView.setModel(self.filterModel)
        moodleTreeView.setSortingEnabled(True)
        moodleTreeView.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        ## TODO: change with minimumSize (?)
        moodleTreeView.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        moodleTreeView.doubleClicked.connect(self.onMoodleTreeViewDoubleClicked)

        ## refresh moodle treeview
        refreshBtn = self.findChild(QPushButton, "refreshBtn")
        refreshBtn.clicked.connect(self.onRefreshBtnClicked)

        if not self.instanceUrl:
            refreshBtn.setEnabled(False)
            log.warning("no server url configured!")

        if not self.token:
            refreshBtn.setEnabled(False)
            log.warning("no server token configured!")


        ## searchbar
        searchBar = self.findChild(QLineEdit, "searchBar")
        searchBar.textChanged.connect(self.onSearchBarTextChanged)
        searchBar.textEdited.connect(self.onSearchBarTextChanged)

        ## select path
        selectPathBtn = self.findChild(QPushButton, "selectPathBtn")
        selectPathBtn.clicked.connect(self.onSelectPathBtnClicked)

        ## progressbar
        self.progressBar = self.findChild(QProgressBar, "downloadProgressBar")

        # self.moodleTreeModel.worker.loaded
        # self.moodleTreeModel.worker.loadedItem.connect(lambda t, item:)

        # local filesystem tab
        self.downloadPath = QDir.homePath()

        self.fileSystemModel = QFileSystemModel()
        self.fileSystemModel.setRootPath(QDir.homePath())

        localTreeView = self.findChild(QTreeView, "localTab")
        localTreeView.setModel(self.fileSystemModel)
        localTreeView.setRootIndex(self.fileSystemModel.index(QDir.homePath()))
        localTreeView.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

        downloadPathEdit = self.findChild(QLineEdit, "downloadPathEdit")
        downloadPathEdit.setText(self.downloadPath)
        downloadPathEdit.editingFinished.connect(self.onDownloadPathEditEditingFinished)

        self.show()

    @pyqtSlot(int)
    def setProgressBarTasks(self, nrTasks):
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(tasks)
        self.progressBar.reset()

    @pyqtSlot()
    def advanceProgressBar(self):
        currentValue = self.progressBar.value()
        self.progressBar.setValue(currentValue + 1);

    @pyqtSlot(int)
    def setProgressBarValue(self, value):
        self.progressBar.setValue(value)

    @pyqtSlot()
    def onRequestTokenBtnClicked(self):
        # TODO: open login dialog
        # TODO: test and maybe check if there is already a token
        # req = moodle.request_token(self.instance_url, user, password)
        pass

    @pyqtSlot(str)
    def onSearchBarTextChanged(self, text):
        moodleTreeView = self.findChild(QTreeView, "moodleTree")
        searchBar = self.findChild(QLineEdit, "searchBar")

        if not text:
            self.filterModel.setFilterRegularExpression(".*")
            moodleTreeView.collapseAll()
            searchBar.setStyleSheet("")
        else:
            regexp = QRegularExpression(text)
            if regexp.isValid():
                self.filterModel.setFilterRegularExpression(regexp)
                moodleTreeView.expandAll()
                searchBar.setStyleSheet("")
            else:
                log.debug("invalid search regular expression, not searching")
                searchBar.setStyleSheet("QLineEdit { color: red; }")

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
                self.downloadPath, QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks)

        if not path:
            return

        self.updateDownloadPath(path)

    @pyqtSlot()
    def onRefreshBtnClicked(self):
        if self.instanceUrl and self.token:
            self.moodleTreeModel.refresh(self.instanceUrl, self.token)
        else:
            # TODO: implement error dialog
            pass

    @pyqtSlot()
    def updateDownloadPath(self, newpath):
        if not self.fileSystemModel.index(newpath).isValid():
            return False

        self.downloadPath = newpath

        downloadPathEdit = self.findChild(QLineEdit, "downloadPathEdit")
        localTreeView = self.findChild(QTreeView, "localTab")

        downloadPathEdit.setText(self.downloadPath)
        localTreeView.setRootIndex(self.fileSystemModel.index(self.downloadPath))

    @pyqtSlot(QModelIndex)
    def onMoodleTreeViewDoubleClicked(self, index):
        realIndex = self.filterModel.mapToSource(index)
        item = self.moodleTreeModel.itemFromIndex(realIndex)

        if item.metadata.type == MoodleItem.Type.FILE:
            log.debug(f"started download from {item.metadata.url}")

            filepath = tempfile.gettempdir()+"/"+item.metadata.title
            self.moodleTreeModel.worker.apihelper.get_file(item.metadata.url, filepath)

            if platform.system() == 'Darwin':       # macOS
                subprocess.Popen(('open', filepath))
            elif platform.system() == 'Windows':    # Windows
                os.startfile(filepath)
            else:                                   # linux variants
                subprocess.Popen(('xdg-open', filepath))

    # this is here to emulate the behavior of setAutoTristate which does not
    # work because of a Qt Bug
    @pyqtSlot(QModelIndex, QModelIndex)
    def onMoodleTreeModelDataChanged(self, topLeft, bottomRight):
        # TODO: this can probably be moved in Item.setData() by creating AutoTriStateRole
        item = self.moodleTreeModel.itemFromIndex(topLeft)

        if item.hasChildren():
            for i in range(0, item.rowCount()):
                # NOTE: this causes the child to emit a signal, which
                # automatically causes to recursively set its children
                item.child(i).setCheckState(item.checkState())


def start(config):
    app = QApplication(sys.argv)
    ex = MuddleWindow(config)
    sys.exit(app.exec())
