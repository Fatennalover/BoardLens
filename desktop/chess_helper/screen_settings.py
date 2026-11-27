"""Confidence, stability and refresh settings for desktop recognition."""
from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QSlider, QSpinBox

from .recognition import ReadQuality


class ScreenSettings(QGroupBox):
    changed = Signal()
    presets = {'Balanced': (70,90,90,2,45), 'Conservative': (78,93,93,3,65),
               'Aggressive': (63,88,87,2,35)}

    def __init__(self):
        super().__init__('Recognition')
        form = QFormLayout(self)
        self.preset = QComboBox()
        self.preset.addItems([*self.presets, 'Custom'])
        form.addRow('Preset',self.preset)
        self.piece = QSlider(Qt.Orientation.Horizontal)
        self.piece.setRange(55,95)
        self.piece.setToolTip('Move left to accept less confident pieces. Move right to require a clearer image.')
        form.addRow('Piece confidence',self.piece)
        self.average, self.grid, self.frames, self.interval = (QSpinBox() for _ in range(4))
        for field, label, limits, suffix, tip in (
            (self.average,'Average confidence',(82,99),'%','Minimum average confidence across all 64 squares.'),
            (self.grid,'Grid confidence',(78,99),'%','How consistently the squares must alternate in the image.'),
            (self.frames,'Position stability',(2,6),' frames','Consecutive matching reads needed to accept a position.'),
            (self.interval,'Scan interval',(25,500),' ms','Requested time between reads. Capture and recognition may take longer.'),
        ):
            field.setRange(*limits);field.setSuffix(' '+suffix if suffix=='%' else suffix)
            field.setToolTip(tip);form.addRow(label,field)
        self.fields = (self.piece,self.average,self.grid,self.frames,self.interval)
        self.restore({})
        for field in self.fields:
            field.valueChanged.connect(self.custom)
        self.preset.currentTextChanged.connect(self.select)

    def select(self, name):
        if name in self.presets:
            for field,value in zip(self.fields,self.presets[name]):
                with QSignalBlocker(field):
                    field.setValue(value)
        self.changed.emit()

    def custom(self, *_):
        with QSignalBlocker(self.preset):
            self.preset.setCurrentText('Custom')
        self.changed.emit()

    def quality(self):
        return ReadQuality(self.piece.value()/100,self.average.value()/100,self.grid.value()/100)

    def snapshot(self):
        return {'preset':self.preset.currentText(),'values':[field.value() for field in self.fields]}

    def restore(self, data):
        if not isinstance(data,dict):
            data = {}
        name = data.get('preset','Balanced')
        if not isinstance(name,str) or self.preset.findText(name)<0:
            name = 'Balanced'
        values = self.presets.get(name,data.get('values'))
        if not isinstance(values,(list,tuple)) or len(values)!=len(self.fields) or not all(type(v) is int for v in values):
            name,values = 'Balanced',self.presets['Balanced']
        with QSignalBlocker(self.preset):
            self.preset.setCurrentText(name)
        for field,value in zip(self.fields,values):
            with QSignalBlocker(field):
                field.setValue(value)
