"""Per-engine installation, with large models excluded from lightweight batches."""
import threading
from PySide6.QtCore import Qt,Signal,QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QPushButton,QHeaderView,QFileDialog,QWidget
from .toggle import ToggleButton as QCheckBox
from . import engine_library,engine_profiles

class EngineLibraryDialog(QDialog):
    progress=Signal(str,str)
    batch_finished=Signal()
    def __init__(self,window):
        super().__init__(window);self.window=window;self.busy=False
        self.setWindowTitle('BoardLens · Optional engine library');self.resize(1020,720)
        layout=QVBoxLayout(self)
        text=QLabel('Select an engine for details. Import an executable built for this computer.');text.setWordWrap(True);layout.addWidget(text)
        self.table=QTableWidget(len(engine_library.ENTRIES),5)
        self.table.setHorizontalHeaderLabels(['Choose','Engine','Rating','Requirements','Status'])
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(58)
        self.table.setWordWrap(True)
        header = self.table.horizontalHeader()
        for column in (1,3):
            header.setSectionResizeMode(column,QHeaderView.ResizeMode.Stretch)
        for column in (0,2,4):
            header.setSectionResizeMode(column,QHeaderView.ResizeMode.ResizeToContents)
        header.setMinimumSectionSize(85)
        layout.addWidget(self.table,1)
        self.choices = []
        for row,entry in enumerate(engine_library.ENTRIES):
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(4,4,4,4)
            checked = QCheckBox()
            checked.setAccessibleName('Download '+entry.label)
            checked.setFixedSize(58,36)
            checked.setEnabled(engine_library.downloadable(entry))
            cell_layout.addWidget(checked,0,Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row,0,cell)
            self.choices.append(checked)
            rating = str(entry.rating) if entry.kind in ('tiny','maia1') else 'See details'
            for column,value in ((1,entry.label),(2,rating),(3,entry.size),(4,'')):
                item=QTableWidgetItem(value);item.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)
                item.setToolTip(engine_profiles.profile(entry.identity)['rating'] if column==2 else value)
                self.table.setItem(row,column,item)
        self.table.horizontalHeader().setSectionResizeMode(4,QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4,128)
        self.details=QLabel()
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.details)
        self.table.currentCellChanged.connect(self.selected_profile)
        self.table.setCurrentCell(0,1)
        buttons=QHBoxLayout();self.selected_button=QPushButton('Download selected');self.light_button=QPushButton('Lightweight batch');self.all_button=QPushButton('Download batch')
        self.selected_button.clicked.connect(self.download_selected)
        self.light_button.clicked.connect(lambda:self.download([e.identity for e in engine_library.ENTRIES if not e.heavy and engine_library.downloadable(e)]))
        self.all_button.clicked.connect(lambda:self.download([e.identity for e in engine_library.ENTRIES if e.kind not in ('toby','allie') and engine_library.downloadable(e)]))
        for button in (self.selected_button,self.light_button,self.all_button):buttons.addWidget(button)
        self.import_button=QPushButton('Import executable…')
        self.import_button.clicked.connect(self.import_engine);buttons.addWidget(self.import_button)
        layout.addLayout(buttons);self.status=QLabel('Nothing downloads automatically.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.progress.connect(self.updated);self.batch_finished.connect(self.finished_downloads);self.refresh()
    def selected_profile(self,row,*_):
        if row>=0:
            entry=engine_library.ENTRIES[row]
            self.details.setText(entry.label+' · '+engine_profiles.description(entry.identity))

    def import_engine(self):
        from . import engine_addons
        row=self.table.currentRow()
        if row<0 or engine_library.ENTRIES[row].kind not in engine_library.ADDON_KINDS:
            self.status.setText('Select Gaia, Toby or Final Rodent first.');return
        entry=engine_library.ENTRIES[row]
        if entry.kind not in ('gaia','rodent','toby'):
            self.status.setText('Select this model for a download instead.');return
        path,_=QFileDialog.getOpenFileName(self,'Select the engine executable')
        if not path:return
        self.status.setText('Checking '+entry.label+'…')
        def verify():
            try:
                engine_addons.set_import(entry,path)
                self.progress.emit(entry.identity,'Verified · ready')
            except Exception as exc:self.progress.emit(entry.identity,'Could not import: '+str(exc))
            self.batch_finished.emit()
        threading.Thread(target=verify,daemon=True).start()

    def refresh(self):
        for row,entry in enumerate(engine_library.ENTRIES):
            if engine_library.available(entry) and entry.kind != 'custom':
                status = 'Installed / ready'
            else:
                status = 'Not installed' if engine_library.downloadable(entry) else 'Import executable'
            self.table.item(row,4).setText(status)
    def download_selected(self):
        self.download([entry.identity for entry,choice in zip(engine_library.ENTRIES,self.choices) if choice.isChecked()])
    def download(self,identities):
        if self.busy:return
        if not identities:self.status.setText('Check one or more engines first.');return
        self.busy=True
        for button in (self.selected_button,self.light_button,self.all_button):button.setEnabled(False)
        self.status.setText('Installing selected engines… Large runtimes can take a few minutes. Closing this window keeps the current download running.')
        def work():
            for identity in identities:
                self.progress.emit(identity,'Downloading…')
                try:
                    entry=engine_library.BY_ID[identity]
                    if not engine_library.available(entry):engine_library.install(identity)
                    self.progress.emit(identity,'Installed / ready')
                except Exception as exc:self.progress.emit(identity,'Failed: '+str(exc))
            self.batch_finished.emit()
        threading.Thread(target=work,daemon=True,name='BoardLens-library').start()
    def updated(self,identity,status):
        row=next(i for i,entry in enumerate(engine_library.ENTRIES) if entry.identity==identity)
        self.table.item(row,4).setText(status)
        self.table.item(row,4).setToolTip(status)
        self.status.setText(engine_library.BY_ID[identity].label+' · '+status)
    def finished_downloads(self):
        self.busy=False
        for button in (self.selected_button,self.light_button,self.all_button):button.setEnabled(True)
        self.window.refresh_engine_selectors();self.window.engine_configuration_changed();self.status.setText('Download batch finished. Select an installed engine manually; failed rows show the reason.')
