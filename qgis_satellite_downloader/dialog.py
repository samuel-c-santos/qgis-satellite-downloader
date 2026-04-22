import os
import sys
import threading
import logging
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QLineEdit, QPushButton, QComboBox, QCheckBox, 
                               QProgressBar, QTextEdit, QFrame, QGridLayout,
                               QGroupBox, QRadioButton, QFileDialog, QDoubleSpinBox, QMessageBox)
from qgis.PyQt.QtCore import Qt, pyqtSignal, QObject
from qgis.core import (QgsProject, QgsRasterLayer, QgsMessageLog, Qgis, 
                       QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsVectorLayer, QgsGeometry, QgsFeature, QgsFields)
from qgis.gui import QgsMessageBar, QgsMapCanvas, QgsCollapsibleGroupBox

# Add plugin directory to path to import internal scripts
plugin_dir = os.path.dirname(__file__)
scripts_dir = os.path.join(plugin_dir, 'scripts')
if scripts_dir not in sys.path:
    sys.path.append(scripts_dir)

import ee
try:
    from scripts.gee_utils import (initialize_gee, get_sentinel_image, get_landsat_image, 
                                 get_download_url, download_image, get_cbers_image_inpe, 
                                 check_cbers_deps, build_planet_wmts_uri, 
                                 build_planet_layer_name, build_planet_layer_title,
                                 get_planet_api_key)
except ImportError:
    try:
        from gee_utils import (initialize_gee, get_sentinel_image, get_landsat_image, 
                             get_download_url, download_image, get_cbers_image_inpe, 
                             check_cbers_deps, build_planet_wmts_uri, 
                             build_planet_layer_name, build_planet_layer_title,
                             get_planet_api_key)
    except ImportError as e:
        QgsMessageLog.logMessage(f"Erro ao importar scripts: {e}", "QGIS Satellite Downloader", Qgis.MessageLevel.Critical)

class LogSignal(QObject):
    log_received = pyqtSignal(str, int) # message, level
    load_layer = pyqtSignal(str, str) # filepath, filename
    load_wmts_layer = pyqtSignal(str, str) # uri, title
    finished = pyqtSignal()

class QgsLogHandler(logging.Handler):
    def __init__(self, signal):
        super().__init__()
        self.signal = signal

    def emit(self, record):
        msg = self.format(record)
        self.signal.log_received.emit(msg, record.levelno)

class QGISGeoDownloaderDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("QGIS Satellite Downloader - Geo Downloader")
        self.setMinimumWidth(500)
        self.setup_ui()
        
        # Logging setup
        self.log_signal = LogSignal()
        self.log_signal.log_received.connect(self.append_log)
        self.log_signal.load_layer.connect(self.add_layer_to_qgis)
        self.log_signal.load_wmts_layer.connect(self.add_wmts_layer_to_qgis)
        self.log_signal.finished.connect(self.on_finished)
        
        self.logger = logging.getLogger('gee_utils')
        self.handler = QgsLogHandler(self.log_signal)
        self.handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.INFO)
        
        self._is_running = False

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # --- Parameters Group ---
        params_group = QGroupBox("Parâmetros do Satélite")
        params_layout = QGridLayout()
        params_group.setLayout(params_layout)

        # Satellite
        params_layout.addWidget(QLabel("Satélite:"), 0, 0)
        self.sat_combo = QComboBox()
        self.sat_combo.addItems(["Sentinel", "Landsat", "CBERS-4A (MUX/WPM)", "Planet Basemap"])
        self.sat_combo.currentTextChanged.connect(self.on_satellite_changed)
        params_layout.addWidget(self.sat_combo, 0, 1)

        # Years
        params_layout.addWidget(QLabel("Anos (ex: 2023 ou 2020-2024):"), 1, 0)
        self.year_entry = QLineEdit("2023-2024")
        params_layout.addWidget(self.year_entry, 1, 1)

        layout.addWidget(params_group)

        # --- Dynamic Options Group ---
        self.dynamic_group = QGroupBox("Opções do Satélite")
        self.dynamic_layout = QVBoxLayout()
        self.dynamic_group.setLayout(self.dynamic_layout)
        layout.addWidget(self.dynamic_group)
        
        self.update_dynamic_fields(self.sat_combo.currentText())

        # --- QGIS Integration ---
        qgis_group = QGroupBox("Integração QGIS")
        qgis_layout = QVBoxLayout()
        qgis_group.setLayout(qgis_layout)
        
        self.add_to_canvas_check = QCheckBox("Carregar resultado no mapa ao concluir")
        self.add_to_canvas_check.setChecked(True)
        qgis_layout.addWidget(self.add_to_canvas_check)
        
        self.use_extent_check = QCheckBox("Usar Extensão Atual do Mapa")
        qgis_layout.addWidget(self.use_extent_check)
        
        # Layer Extent Option
        layer_extent_layout = QHBoxLayout()
        self.use_layer_check = QCheckBox("Usar Extensão de Camada:")
        self.layer_combo = QComboBox()
        self.refresh_layer_btn = QPushButton("🔄")
        self.refresh_layer_btn.setFixedWidth(30)
        self.refresh_layer_btn.clicked.connect(self.populate_layers)
        
        layer_extent_layout.addWidget(self.use_layer_check)
        layer_extent_layout.addWidget(self.layer_combo)
        layer_extent_layout.addWidget(self.refresh_layer_btn)
        qgis_layout.addLayout(layer_extent_layout)
        
        # Ensure only one extent mode is active
        self.use_extent_check.toggled.connect(lambda checked: self.use_layer_check.setChecked(False) if checked else None)
        self.use_layer_check.toggled.connect(lambda checked: self.use_extent_check.setChecked(False) if checked else None)
        
        self.populate_layers()
        qgis_layout.addWidget(self.add_to_canvas_check)
        layout.addWidget(qgis_group)

        # --- Output Directory ---
        output_group = QGroupBox("Pasta de Saída")
        output_layout = QHBoxLayout()
        output_group.setLayout(output_layout)
        
        self.output_entry = QLineEdit(os.path.join(os.path.expanduser("~"), "QGIS Satellite Downloader_Downloads"))
        output_layout.addWidget(self.output_entry)
        
        self.browse_btn = QPushButton("Procurar...")
        self.browse_btn.clicked.connect(self.browse_output_directory)
        output_layout.addWidget(self.browse_btn)
        
        layout.addWidget(output_group)

        # --- Advanced Options ---
        self.advanced_group = QgsCollapsibleGroupBox("Opções Avançadas")
        self.advanced_group.setCollapsed(True)
        advanced_layout = QGridLayout()
        self.advanced_group.setLayout(advanced_layout)
        
        advanced_layout.addWidget(QLabel("Fator de Buffer (Área ao redor):"), 0, 0)
        self.buffer_spin = QDoubleSpinBox()
        self.buffer_spin.setRange(1.0, 10.0)
        self.buffer_spin.setSingleStep(0.5)
        self.buffer_spin.setValue(2.0)
        advanced_layout.addWidget(self.buffer_spin, 0, 1)
        
        advanced_layout.addWidget(QLabel("Método de Composição:"), 1, 0)
        self.method_combo = QComboBox()
        self.method_combo.addItem("Mediana (Mais limpa)", "median")
        self.method_combo.addItem("Melhor Imagem (Menor Nuvens)", "best")
        advanced_layout.addWidget(self.method_combo, 1, 1)
        
        layout.addWidget(self.advanced_group)

        # --- Dependency Alert ---
        has_deps, dep_error = check_cbers_deps()
        if not has_deps:
            self.dep_group = QGroupBox("Ferramentas Faltando")
            dep_layout = QVBoxLayout()
            self.dep_group.setLayout(dep_layout)
            
            label = QLabel(f"⚠️ Erro nas ferramentas CBERS: {dep_error}")
            label.setWordWrap(True)
            dep_layout.addWidget(label)
            
            self.install_btn = QPushButton("FORÇAR REINSTALAÇÃO CBERS")
            self.install_btn.clicked.connect(self.install_dependencies)
            self.install_btn.setStyleSheet("background-color: #d35400; color: white; font-weight: bold;")
            dep_layout.addWidget(self.install_btn)
            
            layout.addWidget(self.dep_group)

        # --- Footer ---
        footer_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        footer_layout.addWidget(self.progress_bar)
        
        self.download_btn = QPushButton("INICIAR DOWNLOAD")
        self.download_btn.clicked.connect(self.start_download)
        self.download_btn.setStyleSheet("font-weight: bold; height: 30px;")
        footer_layout.addWidget(self.download_btn)
        
        layout.addLayout(footer_layout)

        # Log Terminal
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        layout.addWidget(self.log_text)

    def update_dynamic_fields(self, sat):
        # Clear dynamic layout
        while self.dynamic_layout.count():
            item = self.dynamic_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if "Landsat" in sat:
            self.dynamic_layout.addWidget(QLabel("Selecionar Semestre:"))
            self.semester_combo = QComboBox()
            self.semester_combo.addItems(["1º Semestre", "2º Semestre", "Ambos"])
            self.dynamic_layout.addWidget(self.semester_combo)
        elif "Planet" in sat:
            self.dynamic_layout.addWidget(QLabel("Tipo de Mosaico:"))
            self.planet_type_combo = QComboBox()
            self.planet_type_combo.addItems(["Mensal", "Trimestral", "Mais Recente Mensal", "Mais Recente Trimestral"])
            self.planet_type_combo.currentTextChanged.connect(self._on_planet_type_changed)
            self.dynamic_layout.addWidget(self.planet_type_combo)

            self.planet_month_group = QFrame()
            month_grid = QGridLayout(self.planet_month_group)
            self.planet_month_checks = []
            months = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
            for i, name in enumerate(months):
                cb = QCheckBox(name)
                month_grid.addWidget(cb, i // 4, i % 4)
                self.planet_month_checks.append(cb)
            self.dynamic_layout.addWidget(self.planet_month_group)

            self.planet_quarter_combo = QComboBox()
            self.planet_quarter_combo.addItems(["Q1 (Jan-Mar)", "Q2 (Abr-Jun)", "Q3 (Jul-Set)", "Q4 (Out-Dez)", "Todos os Trimestres"])
            self.planet_quarter_combo.setVisible(False)
            self.dynamic_layout.addWidget(self.planet_quarter_combo)

            self._on_planet_type_changed(self.planet_type_combo.currentText())
        else: # Sentinel or CBERS
            self.sentinel_mode_semester = QRadioButton("Composição por Semestre")
            self.sentinel_mode_year = QRadioButton("Análise Anual (Meses)")
            self.sentinel_mode_semester.setChecked(True)
            self.dynamic_layout.addWidget(self.sentinel_mode_semester)
            self.dynamic_layout.addWidget(self.sentinel_mode_year)

            # Month Grid (only visible if year mode is selected)
            self.month_group = QFrame()
            month_grid = QGridLayout(self.month_group)
            self.month_checks = []
            months = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
            for i, name in enumerate(months):
                cb = QCheckBox(name)
                if i in [5, 6, 7]: cb.setChecked(True) # JJA default
                month_grid.addWidget(cb, i // 4, i % 4)
                self.month_checks.append(cb)
            
            self.dynamic_layout.addWidget(self.month_group)
            self.month_group.setVisible(False)
            
            self.sentinel_mode_year.toggled.connect(self.month_group.setVisible)

    def _on_planet_type_changed(self, text):
        is_monthly = "Mensal" in text and "Recente" not in text
        is_quarterly = "Trimestral" in text and "Recente" not in text
        is_latest = "Recente" in text
        self.planet_month_group.setVisible(is_monthly)
        self.planet_quarter_combo.setVisible(is_quarterly)
        self.year_entry.setEnabled(not is_latest)
        if is_latest:
            self.year_entry.setEnabled(False)
        else:
            self.year_entry.setEnabled(True)

    def populate_layers(self):
        self.layer_combo.clear()
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            self.layer_combo.addItem(layer.name(), layer.id())

    def browse_output_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Selecionar Pasta de Saída", self.output_entry.text())
        if dir_path:
            self.output_entry.setText(dir_path)

    def on_satellite_changed(self, text):
        """Update UI options based on selected satellite."""
        is_cbers = "CBERS" in text
        is_planet = "Planet" in text
        self.method_combo.setEnabled(not is_cbers and not is_planet)
        self.buffer_spin.setEnabled(not is_planet)
        if is_cbers:
            self.method_combo.setToolTip("CBERS utiliza a melhor cena disponível (menor cobertura de nuvens) do INPE.")
        elif is_planet:
            self.method_combo.setToolTip("Planet utiliza mosaicos WMTS — composição não se aplica.")
        else:
            self.method_combo.setToolTip("")
        
        if is_planet:
            self.download_btn.setText("ADICIONAR AO MAPA")
            self.add_to_canvas_check.setChecked(True)
            self.add_to_canvas_check.setEnabled(False)
        else:
            self.download_btn.setText("INICIAR DOWNLOAD")
            self.add_to_canvas_check.setEnabled(True)
        
        self.update_dynamic_fields(text)

    def append_log(self, message, level):
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def start_download(self):
        if self._is_running:
            return
            
        self._is_running = True
        self.download_btn.setEnabled(False)
        self.progress_bar.setRange(0, 0) # Indeterminate
        
        self.thread = threading.Thread(target=self.run_process)
        self.thread.daemon = True
        self.thread.start()

    def on_finished(self):
        self._is_running = False
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.download_btn.setEnabled(True)

    def install_dependencies(self):
        """Installs the required CBERS dependencies using pip."""
        reply = QMessageBox.question(self, "Instalação", 
                                   "Isso irá instalar as bibliotecas cbers4asat, rasterio e outras no seu QGIS. \n\n"
                                   "O processo ocorrerá em uma JANELA PRETA (Terminal) separada. \n"
                                   "Deseja continuar?", QMessageBox.Yes | QMessageBox.No)
        
        if reply != QMessageBox.Yes:
            return

        self.install_btn.setEnabled(False)
        self.install_btn.setText("INSTALANDO... AGUARDE")
        self.append_log("⏳ Iniciando instalação de dependências via Terminal externo...", 0)
        
        def run_install():
            import sys
            import io
            try:
                # We use internal pip in-process to guarantee it runs inside 
                # the CURRENT QGIS environment, completely bypassing Windows subprocess issues.
                from pip._internal import main as pip_main
                from unittest.mock import patch
                
                args = ["install", "--upgrade", "--user", "cbers4asat", "rasterio", "geopandas", "shapely", "scikit-image", "numpy<2.0", "geomet", "geojson"]
                
                # QGIS threads don't have stdout/stderr, which crashes pip when it tries to print progress
                dummy_out = io.StringIO()
                dummy_err = io.StringIO()
                
                # pip_main may call sys.exit, which would crash QGIS. We patch it.
                # We also patch stdout and stderr to prevent the NoneType error
                with patch.object(sys, 'exit', return_value=None), \
                     patch.object(sys, 'stdout', dummy_out), \
                     patch.object(sys, 'stderr', dummy_err):
                    result = pip_main(args)
                
                if result == 0 or result is None:
                    self.log_signal.log_received.emit("✅ Instalação concluída na memória do QGIS! Por favor, REINICIE o QGIS agora.", 0)
                else:
                    self.log_signal.log_received.emit(f"⚠️ O instalador retornou o código {result}. Tente reiniciar o QGIS.", 1)
            except Exception as e:
                self.log_signal.log_received.emit(f"❌ Erro na instalação interna: {e}", 2)

        threading.Thread(target=run_install, daemon=True).start()

    def run_process(self):
        try:
            # Inputs
            years_raw = self.year_entry.text()
            sat = self.sat_combo.currentText().lower()
            
            years = []
            if '-' in years_raw:
                start, end = map(int, years_raw.split('-'))
                years = list(range(start, end + 1))
            else:
                years = [int(y) for y in years_raw.split(',')]

            is_planet = "planet" in sat.lower()
            is_cbers = "cbers" in sat.lower()

            buffer_factor = self.buffer_spin.value()
            comp_method = self.method_combo.currentData()

            # Output dir
            output_dir = self.output_entry.text()
            if not output_dir:
                output_dir = os.path.join(os.path.expanduser("~"), "QGIS Satellite Downloader_Downloads")
            os.makedirs(output_dir, exist_ok=True)

            if not self._is_running: return

            # Planet WMTS branch (no GEE, no download, just add WMTS layers)
            if is_planet:
                for year in years:
                    if not self._is_running: break
                    planet_type = self.planet_type_combo.currentText()

                    if "Mais Recente" in planet_type:
                        if "Mensal" in planet_type:
                            layer_name = build_planet_layer_name('latest_monthly')
                        else:
                            layer_name = build_planet_layer_name('latest_quarterly')
                        title = build_planet_layer_title(layer_name)
                        self.logger.info(f"  🛰️ Adicionando mosaico Planet: {title}")
                        uri = build_planet_wmts_uri(layer_name)
                        if uri:
                            self.log_signal.load_wmts_layer.emit(uri, title)
                    elif "Mensal" in planet_type:
                        selected_months = [i+1 for i, cb in enumerate(self.planet_month_checks) if cb.isChecked()]
                        for month in selected_months:
                            if not self._is_running: break
                            layer_name = build_planet_layer_name('monthly', year=year, month=month)
                            title = build_planet_layer_title(layer_name)
                            self.logger.info(f"  🛰️ Adicionando mosaico Planet: {title}")
                            uri = build_planet_wmts_uri(layer_name)
                            if uri:
                                self.log_signal.load_wmts_layer.emit(uri, title)
                    elif "Trimestral" in planet_type:
                        quarter_text = self.planet_quarter_combo.currentText()
                        if "Todos" in quarter_text:
                            quarters = [1, 2, 3, 4]
                        else:
                            quarters = [int(quarter_text[1])]
                        for quarter in quarters:
                            if not self._is_running: break
                            layer_name = build_planet_layer_name('quarterly', year=year, quarter=quarter)
                            title = build_planet_layer_title(layer_name)
                            self.logger.info(f"  🛰️ Adicionando mosaico Planet: {title}")
                            uri = build_planet_wmts_uri(layer_name)
                            if uri:
                                self.log_signal.load_wmts_layer.emit(uri, title)
            else:
                # Initialize GEE (not needed for Planet)
                initialize_gee()

                # Geometry Logic
                if self.use_layer_check.isChecked():
                    layer_id = self.layer_combo.currentData()
                    layer = QgsProject.instance().mapLayer(layer_id)
                    if not layer:
                        self.logger.error("  ❌ Camada selecionada não encontrada.")
                        return
                    
                    self.logger.info(f"\n🌍 Área: Extensão da Camada '{layer.name()}'")
                    extent = layer.extent()
                    src_crs = layer.crs()
                    dest_crs = QgsCoordinateReferenceSystem("EPSG:4326")
                    if src_crs != dest_crs:
                        xform = QgsCoordinateTransform(src_crs, dest_crs, QgsProject.instance())
                        extent = xform.transformBoundingBox(extent)
                    
                    region = ee.Geometry.Rectangle([extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()])
                    label = f"Layer_{layer.name()}"
                else:
                    self.logger.info("\n🌍 Área: Extensão Atual do Mapa")
                    extent = self.iface.mapCanvas().extent()
                    src_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
                    dest_crs = QgsCoordinateReferenceSystem("EPSG:4326")
                    if src_crs != dest_crs:
                        xform = QgsCoordinateTransform(src_crs, dest_crs, QgsProject.instance())
                        extent = xform.transformBoundingBox(extent)
                    
                    region = ee.Geometry.Rectangle([extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()])
                    label = "Map_Extent"

                car_dir = os.path.join(output_dir, label)
                os.makedirs(car_dir, exist_ok=True)

                for year in years:
                    if not self._is_running: break
                    if "sentinel" in sat.lower():
                        if self.sentinel_mode_year.isChecked():
                            # Monthly mode
                            selected_months = [i+1 for i, cb in enumerate(self.month_checks) if cb.isChecked()]
                            for month in selected_months:
                                self.logger.info(f"  📅 {year}-{month:02d} (Sentinel)")
                                img = get_sentinel_image(region, year, month, month, method=comp_method)
                                if img:
                                    self._download_and_load(img, region, year, f"{month:02d}", car_dir, 10, "Sentinel", buffer_factor)
                        else:
                            # Semester mode
                            for sem in [1, 2]:
                                start_m, end_m = (1, 6) if sem == 1 else (7, 12)
                                self.logger.info(f"  📅 {year} S{sem} (Sentinel)")
                                img = get_sentinel_image(region, year, start_m, end_m, method=comp_method)
                                if img:
                                    self._download_and_load(img, region, year, f"S{sem}", car_dir, 10, "Sentinel", buffer_factor)
                    elif is_cbers:
                        # CBERS (INPE)
                        if self.sentinel_mode_year.isChecked():
                            selected_months = [i+1 for i, cb in enumerate(self.month_checks) if cb.isChecked()]
                            if selected_months:
                                self.logger.info(f"  📅 {year} (Meses selecionados) - CBERS via INPE")
                                final_path = get_cbers_image_inpe(region, year, selected_months, car_dir, scale_factor=buffer_factor)
                                if final_path and self.add_to_canvas_check.isChecked():
                                    self.log_signal.load_layer.emit(final_path, os.path.basename(final_path))
                        else:
                            for sem in [1, 2]:
                                self.logger.info(f"  📅 {year} S{sem} - CBERS via INPE")
                                months = [1,2,3,4,5,6] if sem == 1 else [7,8,9,10,11,12]
                                final_path = get_cbers_image_inpe(region, year, months, car_dir, scale_factor=buffer_factor)
                                if final_path and self.add_to_canvas_check.isChecked():
                                    self.log_signal.load_layer.emit(final_path, os.path.basename(final_path))
                    else:
                        # Landsat
                        sem_choice = self.semester_combo.currentText()
                        semesters = [1] if sem_choice == "1º Semestre" else [2] if sem_choice == "2º Semestre" else [1, 2]
                        for sem in semesters:
                            self.logger.info(f"  📅 {year} S{sem} (Landsat)")
                            img, _ = get_landsat_image(region, year, sem, method=comp_method)
                            if img:
                                self._download_and_load(img, region, year, f"S{sem}", car_dir, 30, "Landsat", buffer_factor)

            self.logger.info("\n✨ Processo concluído!")

        except Exception as e:
            self.logger.error(f"Erro crítico: {e}")

        
        finally:
            self.log_signal.finished.emit()

    def _download_and_load(self, img, region, year, suffix, car_dir, scale, prefix, buffer_factor=2.0):
        url = get_download_url(img, region, scale=scale, scale_factor=buffer_factor)
        filename = f"{prefix}_{year}_{suffix}.tif"
        filepath = os.path.join(car_dir, filename)
        if download_image(url, filepath):
            if self.add_to_canvas_check.isChecked():
                self.log_signal.log_received.emit(f"  📥 Carregando no QGIS: {filename}", logging.INFO)
                self.log_signal.load_layer.emit(filepath, filename)

    def add_layer_to_qgis(self, filepath, filename):
        # Normalize path for QGIS (forward slashes are safer on Windows for QGIS API)
        filepath = os.path.normpath(filepath).replace("\\", "/")
        layer = QgsRasterLayer(filepath, filename)
        
        if layer.isValid():
            try:
                # Safer check for resampling methods (compatibility with older QGIS)
                if hasattr(layer, "setZoomInResamplingMethod"):
                    # Try to get Cubic method. 2 is the standard enum value for Cubic.
                    resampling_enum = getattr(QgsRasterLayer, "ResamplingMethod", None)
                    method = getattr(resampling_enum, "Cubic", 2) if resampling_enum else 2
                    layer.setZoomInResamplingMethod(method)
                    layer.setZoomOutResamplingMethod(method)
                else:
                    # Fallback for QGIS < 3.16 where it might be in the resamplingFilter
                    res_filter = layer.resamplingFilter() if hasattr(layer, "resamplingFilter") else None
                    if res_filter:
                        res_filter.setZoomInResamplingMethod(2) # 2 = Cubic
                        res_filter.setZoomOutResamplingMethod(2)
            except Exception as e:
                self.logger.warning(f"  ⚠️ Não foi possível definir a reamostragem cúbica: {e}")
            
            QgsProject.instance().addMapLayer(layer)
        else:
            self.logger.error(f"  ❌ Falha ao carregar camada: {filename}")
            self.logger.error(f"     Arquivo não encontrado ou inválido: {filepath}")

    def add_wmts_layer_to_qgis(self, uri, title):
        layer = QgsRasterLayer(uri, title, "wms")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            self.logger.info(f"  ✅ Camada Planet adicionada: {title}")
        else:
            self.logger.error(f"  ❌ Falha ao carregar camada Planet WMTS: {title}")

