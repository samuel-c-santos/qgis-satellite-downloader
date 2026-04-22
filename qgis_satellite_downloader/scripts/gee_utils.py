import ee
import datetime
import os
import requests
import logging
from dotenv import load_dotenv
import calendar
import urllib.parse
try:
    from qgis.core import QgsMessageLog, Qgis
except ImportError:
    QgsMessageLog = None
import site
import sys
import traceback

# Setup logging
logger = logging.getLogger(__name__)

def check_cbers_deps():
    """Dynamically checks if CBERS dependencies are available and functional."""
    # Ensure user site-packages are always in path for QGIS 3.x
    try:
        user_site = site.getusersitepackages()
        if os.path.exists(user_site) and user_site not in sys.path:
            sys.path.insert(0, user_site) # Insert at front to override conflicting plugins
    except:
        pass

    try:
        # Test imports one by one to find the culprit
        import cbers4asat
        import rasterio
        import geopandas
        import shapely
        import skimage
        import geomet
        import geojson
        return True, ""
    except ImportError as e:
        return False, f"{e}"
    except Exception as e:
        return False, f"Erro de carregamento: {e}"

# Initial check for the UI (button visibility)
HAS_CBERS_DEPS, DEPS_ERROR = check_cbers_deps()

# If deps are OK, import the necessary classes to the global scope
try:
    import rasterio
    import geopandas as gpd
    from cbers4asat import Cbers4aAPI, Collections as coll
    from cbers4asat.tools import rgbn_composite, clip as raster_clip
    from shapely.geometry import Polygon
except Exception as e:
    logger.error(f"❌ Erro crítico ao carregar classes globais: {traceback.format_exc()}")
    if QgsMessageLog:
        QgsMessageLog.logMessage(f"❌ Erro crítico ao carregar classes globais: {e}", "QGIS Satellite Downloader", Qgis.MessageLevel.Critical)

def initialize_gee():
    """Initializes Google Earth Engine using a service account credentials file."""
    # Check if already initialized for this project
    try:
        if ee.data._initialized:
            return
    except:
        pass
    # Look for .env in current or parent directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_dir = os.path.dirname(script_dir)
    env_path = os.path.join(plugin_dir, '.env')
    
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        load_dotenv()
    
    project_id = os.getenv('GEE_PROJECT_ID')
    credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_PATH')
    
    # If credentials_path is relative, make it absolute relative to plugin_dir
    if credentials_path and not os.path.isabs(credentials_path):
        test_path = os.path.join(plugin_dir, credentials_path)
        if os.path.exists(test_path):
            credentials_path = test_path

    if credentials_path and os.path.exists(credentials_path):
        try:
            credentials = ee.ServiceAccountCredentials(None, credentials_path)
            ee.Initialize(credentials, project=project_id)
            logger.info(f"GEE Initialized with local Service Account for project: {project_id}")
        except Exception as e:
            logger.error(f"Failed to initialize GEE with Service Account: {e}")
            raise
    else:
        try:
            ee.Initialize(project=project_id)
            logger.info(f"GEE Initialized with default credentials for project: {project_id}")
        except Exception as e:
            logger.error(f"Failed to initialize GEE: {e}")
            raise

def get_sentinel_image(region, year, start_month, end_month, method='median'):
    """Retrieves a median Sentinel-2 SR image for a given region and time range."""
    import calendar
    _, last_day = calendar.monthrange(year, end_month)
    
    start_date = f"{year}-{start_month:02d}-01"
    end_date = f"{year}-{end_month:02d}-{last_day}"

    collection = (ee.ImageCollection("COPERNICUS/S2_SR")
                  .filterBounds(region)
                  .filterDate(start_date, end_date)
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
                  .select(['B4', 'B3', 'B2']))

    count = collection.size().getInfo()
    if count == 0:
        logger.warning(f"No Sentinel image found for {year}/{start_month}-{end_month} (<10% clouds)")
        return None

    if method == 'best':
        image = collection.sort('CLOUDY_PIXEL_PERCENTAGE').first()
        try:
            date = ee.Date(image.get('system:time_start')).format('YYYY-MM-DD').getInfo()
            logger.info(f"  ✨ Melhor imagem Sentinel selecionada: {date}")
        except:
            pass
        return image
    
    logger.info(f"Found {count} Sentinel images for {year}/{start_month:02d}-{end_month:02d}. Creating median composite...")
    return collection.median()

def get_landsat_image(region, year, semester, method='median'):
    """Retrieves a median Landsat image for a given region and semester."""
    if semester == 1:
        start_date = f"{year}-01-01"
        end_date = f"{year}-06-30"
    else:
        start_date = f"{year}-07-01"
        end_date = f"{year}-12-31"

    if year <= 2011:
        collection_id = "LANDSAT/LT05/C02/T1_L2"
        band_options = ['SR_B5', 'SR_B4', 'SR_B3']
    elif year <= 2013:
        collection_id = "LANDSAT/LE07/C02/T1_L2"
        band_options = ['SR_B3', 'SR_B2', 'SR_B1']
    elif year <= 2021:
        collection_id = "LANDSAT/LC08/C02/T1_L2"
        band_options = ['SR_B6', 'SR_B5', 'SR_B4']
    else:
        collection_id = "LANDSAT/LC09/C02/T1_L2"
        band_options = ['SR_B4', 'SR_B3', 'SR_B2']

    collection = (ee.ImageCollection(collection_id)
                  .filterBounds(region)
                  .filterDate(start_date, end_date)
                  .filter(ee.Filter.lt('CLOUD_COVER', 10)))

    count = collection.size().getInfo()
    if count == 0:
        logger.warning(f"No Landsat image found for {year} S{semester}")
        return None, None

    if method == 'best':
        image = collection.sort('CLOUD_COVER').first()
        try:
            date = ee.Date(image.get('system:time_start')).format('YYYY-MM-DD').getInfo()
            logger.info(f"  ✨ Melhor imagem Landsat selecionada: {date}")
        except:
            pass
        return image.select(band_options), band_options

    logger.info(f"Found {count} Landsat images for {year} S{semester}. Creating median composite...")
    image = collection.median().select(band_options)
    return image, band_options

def get_download_url(image, region, scale=10, scale_factor=2):
    """Generates a GeoTIFF download URL for a clipped image."""
    bounds = region.bounds()
    coords = bounds.coordinates().get(0).getInfo()
    
    xs = [pt[0] for pt in coords]
    ys = [pt[1] for pt in coords]
    xmid = (min(xs) + max(xs)) / 2
    ymid = (min(ys) + max(ys)) / 2
    xrange = (max(xs) - min(xs)) * scale_factor / 2
    yrange = (max(ys) - min(ys)) * scale_factor / 2
    
    expanded_bounds = ee.Geometry.Rectangle([xmid - xrange, ymid - yrange,
                                             xmid + xrange, ymid + yrange])

    url = image.clip(expanded_bounds).getDownloadURL({
        'scale': scale,
        'region': expanded_bounds,
        'format': 'GeoTIFF'
    })
    return url

def download_image(url, output_path):
    """Downloads an image from a GEE URL to a local path."""
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        response = requests.get(url, stream=True, timeout=60)
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"✅ Download complete: {output_path}")
            return True
        else:
            logger.error(f"❌ Failed to download {output_path}: HTTP {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Error downloading {output_path}: {e}")
        return False

def get_cbers_image_inpe(region_ee, year, months, output_dir, scale_factor=2):
    """Downloads and processes CBERS-4A imagery from INPE STAC with an optional border."""
    has_deps, err = check_cbers_deps()
    if not has_deps:
        logger.error(f"❌ Erro nas dependências CBERS: {err}")
        if QgsMessageLog:
            QgsMessageLog.logMessage(f"❌ Erro nas dependências CBERS: {err}", "QGIS Satellite Downloader", Qgis.MessageLevel.Critical)
        return None
    try:
        inpe_email = os.getenv('INPE_EMAIL')
        if not inpe_email:
            logger.error("❌ INPE_EMAIL não configurado no arquivo .env")
            return None

        # Convert GEE region to BBOX [west, south, east, north]
        bounds = region_ee.bounds().coordinates().get(0).getInfo()
        lons = [p[0] for p in bounds]
        lats = [p[1] for p in bounds]
        
        # Calculate center and span with scale_factor (border)
        xmid = (min(lons) + max(lons)) / 2
        ymid = (min(lats) + max(lats)) / 2
        xrange = (max(lons) - min(lons)) * scale_factor / 2
        yrange = (max(lats) - min(lats)) * scale_factor / 2
        
        bbox = [xmid - xrange, ymid - yrange, xmid + xrange, ymid + yrange]
        logger.info(f"📐 BBOX com Borda ({scale_factor}x): {bbox}")
        
        # Shapely polygon for clipping later (using the same expanded area)
        poly_aoi = Polygon([ 
            (bbox[0], bbox[1]), (bbox[2], bbox[1]), 
            (bbox[2], bbox[3]), (bbox[0], bbox[3]) 
        ])

        api = Cbers4aAPI(inpe_email)
        
        start_date = datetime.date(year, min(months), 1)
        _, last_day = calendar.monthrange(year, max(months))
        end_date = datetime.date(year, max(months), last_day)

        logger.info(f"🔍 Buscando CBERS-4A no INPE ({start_date} a {end_date})...")
        
        # We search for MUX (20m) and WPM (8m/2m)
        products = api.query(
            location=bbox,
            initial_date=start_date,
            end_date=end_date,
            cloud=100, # We will sort by cloud later
            limit=50,
            collections=['CBERS4A_WPM_L4_DN']
        )
        
        if not products or not products.get('features'):
            logger.warning(f"⚠️ Nenhuma imagem CBERS encontrada para {year} no período selecionado.")
            return None

        # Sort by cloud cover and take the best
        features = products['features']
        # Note: 'properties' might contain 'cloud_cover' or 'eo:cloud_cover'
        def get_cloud(f):
            p = f.get('properties', {})
            return p.get('cloud_cover', p.get('eo:cloud_cover', 100))
        
        features.sort(key=get_cloud)
        best_feature = features[0]
        scene_id = best_feature['id']
        cloud_val = get_cloud(best_feature)
        date_str = best_feature['properties'].get('datetime', '').split('T')[0]
        
        logger.info(f"✨ Melhor cena CBERS encontrada: {scene_id} ({date_str}, {cloud_val}% nuvens)")

        # Download bands
        # MUX: B5(R), B6(G), B7(B), B8(NIR)
        # WPM: B1(B), B2(G), B3(R), B4(NIR), B0(PAN)
        bands = ['red', 'green', 'blue', 'nir'] # cbers4asat aliases
        
        temp_dir = os.path.join(output_dir, "temp_cbers")
        os.makedirs(temp_dir, exist_ok=True)
        
        logger.info(f"📥 Baixando bandas para {scene_id}...")
        api.download(
            products={'type': 'FeatureCollection', 'features': [best_feature]},
            bands=bands,
            outdir=temp_dir,
            with_folder=True
        )

        # Find the downloaded files
        scene_subdir = os.path.join(temp_dir, scene_id)
        if not os.path.exists(scene_subdir):
            # Sometimes the folder name differs slightly
            subdirs = [d for d in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, d))]
            if subdirs: scene_subdir = os.path.join(temp_dir, subdirs[0])

        files = os.listdir(scene_subdir)
        b_red = next((os.path.join(scene_subdir, f) for f in files if 'BAND3' in f or 'BAND5' in f), None)
        b_green = next((os.path.join(scene_subdir, f) for f in files if 'BAND2' in f or 'BAND6' in f), None)
        b_blue = next((os.path.join(scene_subdir, f) for f in files if 'BAND1' in f or 'BAND7' in f), None)
        b_nir = next((os.path.join(scene_subdir, f) for f in files if 'BAND4' in f or 'BAND8' in f), None)

        if not all([b_red, b_green, b_blue]):
            logger.error("❌ Erro ao localizar bandas baixadas.")
            return None

        # Composite
        composite_path = os.path.join(output_dir, f"CBERS_{scene_id}_STACK.tif")
        logger.info(f"🎨 Criando composição RGB...")
        rgbn_composite(
            red=b_red, green=b_green, blue=b_blue, nir=b_nir,
            filename=os.path.basename(composite_path),
            outdir=output_dir
        )
        
        # Clip to AOI
        final_filename = f"CBERS_{year}_{scene_id[:10]}.tif"
        final_path = os.path.join(output_dir, final_filename)
        logger.info(f"✂️ Recortando para área de interesse...")
        
        try:
            import geopandas as gpd
            # Get raster CRS
            with rasterio.open(composite_path) as src:
                raster_crs = src.crs or "EPSG:3857" # fallback
            
            # Reproject AOI to raster CRS
            gdf_aoi = gpd.GeoDataFrame(index=[0], crs="EPSG:4326", geometry=[poly_aoi])
            gdf_aoi = gdf_aoi.to_crs(raster_crs)
            poly_mask = gdf_aoi.geometry.iloc[0]
            
            raster_clip(
                raster=composite_path,
                mask=poly_mask,
                filename=final_filename,
                outdir=output_dir
            )
        except Exception as clip_err:
            logger.warning(f"⚠️ Erro no recorte projetado: {clip_err}. Tentando recorte simples...")
            raster_clip(
                raster=composite_path,
                mask=poly_aoi,
                filename=final_filename,
                outdir=output_dir
            )
        
        # Cleanup
        try:
            import shutil
            shutil.rmtree(temp_dir)
            if os.path.exists(composite_path): os.remove(composite_path)
        except:
            pass
            
        return final_path

    except Exception as e:
        logger.error(f"❌ Erro no processamento CBERS: {e}")
        return None

def get_planet_api_key():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_dir = os.path.dirname(script_dir)
    env_path = os.path.join(plugin_dir, '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
    planet_api_url = os.getenv('PLANET_API', '')
    if not planet_api_url:
        return None
    parsed = urllib.parse.urlparse(planet_api_url)
    params = urllib.parse.parse_qs(parsed.query)
    api_key = params.get('api_key', [None])[0]
    return api_key

def build_planet_wmts_uri(layer_name):
    api_key = get_planet_api_key()
    if not api_key:
        logger.error("PLANET_API não configurado. Verifique o arquivo .env")
        return None
    wmts_url = f"https://api.planet.com/basemaps/v1/mosaics/wmts?api_key={api_key}"
    encoded_url = urllib.parse.quote(wmts_url, safe='')
    uri = (
        f"crs=EPSG:3857"
        f"&format=image/png"
        f"&layers={layer_name}"
        f"&styles=Default"
        f"&tileMatrixSet=GoogleMapsCompatible15"
        f"&url={encoded_url}"
    )
    return uri

def build_planet_layer_name(mosaic_type, year=None, month=None, quarter=None):
    if mosaic_type == 'latest_monthly':
        return 'Latest Global Monthly'
    elif mosaic_type == 'latest_quarterly':
        return 'Latest Global Quarterly'
    elif mosaic_type == 'monthly':
        return f'global_monthly_{year}_{month:02d}_mosaic'
    elif mosaic_type == 'quarterly':
        return f'global_quarterly_{year}q{quarter}_mosaic'
    return None

def build_planet_layer_title(layer_name):
    if layer_name == 'Latest Global Monthly':
        return 'Planet - Mais Recente Mensal'
    elif layer_name == 'Latest Global Quarterly':
        return 'Planet - Mais Recente Trimestral'
    name = layer_name.replace('global_', '').replace('_mosaic', '')
    if name.startswith('monthly_'):
        parts = name.replace('monthly_', '').split('_')
        if len(parts) == 2:
            return f'Planet Mensal {parts[0]}-{parts[1]}'
    elif name.startswith('quarterly_'):
        import re
        match = re.match(r'quarterly_(\d{4})(q\d)', name)
        if match:
            return f'Planet Trimestral {match.group(1)}-{match.group(2)}'
    return f'Planet {layer_name}'
