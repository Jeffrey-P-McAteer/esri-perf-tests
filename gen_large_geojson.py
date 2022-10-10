
import random
import os
import sys
import tempfile
import glob
import subprocess
import traceback

# ESRI is restrictive about this, so we must download their drivers to a directory
# and set GDAL_DRIVER_PATH so fiona can look up the gdb driver with write support.
def download_and_unpack_to_folder(url, archive_file_name, folder):
    from io import BytesIO
    from urllib.request import urlopen
    from zipfile import ZipFile
    import tarfile
    import gzip
    import io

    with urlopen(url) as resp:
      if '.zip' in archive_file_name:
        with ZipFile(BytesIO(resp.read())) as zfile:
            zfile.extractall(folder)

      elif '.tar.gz' in archive_file_name:
        tar_gz_bytes = resp.read()
        tar_mem = tarfile.open(
          fileobj=io.BytesIO(gzip.decompress( tar_gz_bytes ))
        )
        if not os.path.exists(folder):
          os.makedirs(folder)
        tar_mem.extractall(folder)

      else:
        raise Exception(f'Unknown archive type for archive_file_name={archive_file_name}')


esri_driver_dir = os.path.join(tempfile.gettempdir(), 'esri')
os.makedirs(esri_driver_dir, exist_ok=True)
num_driver_dlls = len([x for x in glob.glob(os.path.join(esri_driver_dir, '**', '*.dll'), recursive=True)])
num_driver_sos = len([x for x in glob.glob(os.path.join(esri_driver_dir, '**', '*.so'), recursive=True)])
if num_driver_dlls < 1:
  download_and_unpack_to_folder(
    'https://raw.githubusercontent.com/Esri/file-geodatabase-api/master/FileGDB_API_1.5.2/FileGDB_API_VS2019.zip',
    'FileGDB_API_VS2019.zip',
    esri_driver_dir
  )
if num_driver_sos < 1:
  download_and_unpack_to_folder(
    'https://raw.githubusercontent.com/Esri/file-geodatabase-api/master/FileGDB_API_1.5.2/FileGDB_API_RHEL7_64.tar.gz',
    'FileGDB_API_RHEL7_64.tar.gz',
    esri_driver_dir
  )
# Find all folders w/ *.dll and *.so files
driver_dirs = []
for file in glob.glob(os.path.join(esri_driver_dir, '**', '*.so'), recursive=True):
  file_parent = os.path.dirname(file)
  if not file_parent in driver_dirs:
    driver_dirs.append(file_parent)
for file in glob.glob(os.path.join(esri_driver_dir, '**', '*.dll'), recursive=True):
  file_parent = os.path.dirname(file)
  if not file_parent in driver_dirs:
    driver_dirs.append(file_parent)

# If we have not yet set the following paths, set them and re-launch python.exe because ctypes needs variables set BEFORE the process executes. -_-
all_driver_dirs_in_ld_lib_path = all([ driver_dir in os.environ.get('PATH', '') for driver_dir in driver_dirs ])
if not all_driver_dirs_in_ld_lib_path:
  os.environ['GDAL_DRIVER_PATH'] = os.pathsep.join( [x for x in [*(os.environ.get('GDAL_DRIVER_PATH', '').split(os.pathsep)), *driver_dirs ] if len(x) > 0] )
  # print(f'GDAL_DRIVER_PATH = {os.environ["GDAL_DRIVER_PATH"]}')
  os.environ['PATH'] = os.pathsep.join( [x for x in [*(os.environ.get('PATH', '').split(os.pathsep)), *driver_dirs ] if len(x) > 0] )
  os.environ['LD_LIBRARY_PATH'] = os.pathsep.join( [x for x in [*(os.environ.get('LD_LIBRARY_PATH', '').split(os.pathsep)), *driver_dirs ] if len(x) > 0] )
  # Re-execute ourselves as sub-process
  #sys.exit( os.execv(sys.argv[0], sys.argv) )
  exited_proc = subprocess.run([
    sys.executable, *sys.argv[:1]
  ])
  sys.exit(exited_proc.returncode)


# ^^ The above does not give us access to the write-enabled GDAL driver,
#    so we rig a CTypes wrapper as best we can to test it's write capabilities

# Due to the cdll module's initialization being designed by a toaster which accidentially gained sentience, we MUST modify PATH and LD_LIBRARY_PATH before importing it
import ctypes
class FileGDB_API():
  @staticmethod
  def search_for_lib(lib_name):
    lib_full_path = None
    for search_d in os.environ.get('GDAL_DRIVER_PATH', '').split(os.pathsep):
      maybe_lib_full_path = os.path.join(search_d, lib_name)
      if os.path.exists(maybe_lib_full_path):
        lib_full_path = maybe_lib_full_path
    if lib_full_path is None:
      raise Exception(f'Cannot find {lib_name}!')
    return lib_full_path


  def __init__(self, gdb_directory_path):
    self.gdb_directory_path = gdb_directory_path
    
    self.lib_name = 'libFileGDBAPI.so'
    if os.name == 'nt':
      self.lib_name = 'FileGDBAPI.dll'
    lib_full_path = FileGDB_API.search_for_lib(self.lib_name)
    lib_dependencies = [
      'libfgdbunixrtl.so',
    ]
    if os.name == 'nt':
      lib_dependencies = [
        'FileGDBAPID.dll',
      ]

    try:
      ctypes.CDLL(lib_full_path, mode=ctypes.RTLD_GLOBAL)
    except:
      traceback.print_exc()

    for dependency in lib_dependencies:
      dependency_lib = ctypes.CDLL(
        FileGDB_API.search_for_lib(dependency), mode=ctypes.RTLD_GLOBAL # RTLD_GLOBAL is what allows the next ctypes.CDLL to resolve symbols
      )

    self._FileGDB_API = ctypes.CDLL(lib_full_path, mode=ctypes.RTLD_GLOBAL)

    print(f'{self.lib_name} loaded as {self._FileGDB_API}')


  def read(self):
    raise Exception('TODO write me')

  def write(self, geodataframe):
    print(f'geodataframe={geodataframe}')
    
    return None

# python -m pip install --user geojson
import geojson

# python -m pip install --user geopandas
import geopandas
# python -m pip install --user pyarrow
import pyarrow.feather # Dependency of geopandas for feather file support
import fiona # Also dependency of geopandas, used to query file geodatabase driver via fiona.supported_drivers
# python -m pip install --user linetimer
from linetimer import CodeTimer

#num_to_gen = 1000000
num_to_gen = 100000
geojson_file = '/mnt/scratch/data.geojson'
geofeather_lz4_file = '/mnt/scratch/data.geofeather.lz4'
geofeather_zstd_file = '/mnt/scratch/data.geofeather.zstd'
sqlite_file = '/mnt/scratch/data.sqlite.db'
file_gdb_dirname = '/mnt/scratch/data.gdb'

if not os.path.exists(geojson_file):
  features = []
  with CodeTimer(f'Generate {num_to_gen} random features ', unit='s'):
    for i in range(0, num_to_gen): # Generate 1 million random features
      if i % (int(num_to_gen / 100)) == 0:
        print('.', flush=True, end='')
      features.append(
        geojson.Feature(geometry=geojson.Point( (random.uniform(-45.0, 45.0), random.uniform(-45.0, 45.0)) ), properties={
          "name": ""+random.choice(["Name A", "Name B", "Name C", "Another Name", "Yet another one", "Look this has special characters!"]),
          "description": ' '.join([ str(random.uniform(0.0, 10000.0)) for _ in range(0, random.randint(10, 100) ) ]),
        })
      )
    print('')

  with CodeTimer(f'Dump {num_to_gen} random features to {geojson_file}', unit='s'):
    fc = geojson.FeatureCollection(features)
    with open(geojson_file, 'w') as fd:
      geojson.dump(fc, fd)

  features = [] # gc memory pls
  fc = None

print(f'Testing against {geojson_file} with {num_to_gen} features.')
os.system(f'ls -alh {geojson_file}')

# with CodeTimer(f'Convert {geojson_file} to {geofeather_lz4_file}', unit='s'):
#   with CodeTimer(f'Read {geojson_file}', unit='s'):
#     geodata = geopandas.read_file(geojson_file)
#   #print(f'geodata={geodata}')
#   with CodeTimer(f'Write {geofeather_lz4_file}', unit='s'):
#     geodata.to_feather(geofeather_lz4_file, compression='lz4')

# os.system(f'ls -alh {geojson_file}')
# os.system(f'ls -alh {geofeather_lz4_file}')

# with CodeTimer(f'Convert {geojson_file} to {geofeather_zstd_file}', unit='s'):
#   with CodeTimer(f'Read {geojson_file}', unit='s'):
#     geodata = geopandas.read_file(geojson_file)
#   #print(f'geodata={geodata}')
#   with CodeTimer(f'Write {geofeather_zstd_file}', unit='s'):
#     geodata.to_feather(geofeather_zstd_file, compression='zstd')
  
# os.system(f'ls -alh {geojson_file}')
# os.system(f'ls -alh {geofeather_zstd_file}')

# with CodeTimer(f'Convert {geojson_file} to {sqlite_file}', unit='s'):
#   with CodeTimer(f'Read {geojson_file}', unit='s'):
#     geodata = geopandas.read_file(geojson_file)
#   #print(f'geodata={geodata}')
#   with CodeTimer(f'Write {sqlite_file}', unit='s'):
#     geodata.to_file(sqlite_file, driver='SQLite')
  
# os.system(f'ls -alh {geojson_file}')
# os.system(f'ls -alh {sqlite_file}')


with CodeTimer(f'Convert {geojson_file} to {file_gdb_dirname}', unit='s'):
  with CodeTimer(f'Read {geojson_file}', unit='s'):
    geodata = geopandas.read_file(geojson_file)
  #print(f'geodata={geodata}')
  with fiona.drivers():
    print(f'fiona.supported_drivers={fiona.supported_drivers}')
    fgdb_driver_name = None
    try:
      fgdb_driver_name = next(iter([
        driver_name for driver_name, driver_capabilities in fiona.supported_drivers.items() if 'gdb' in driver_name.lower() and 'w' in driver_capabilities.lower()
      ]))
    except:
      pass
    if fgdb_driver_name is None:
      lib_fgdb = FileGDB_API(file_gdb_dirname)
      lib_fgdb.write(geodata)
    else:
      print(f'fgdb_driver_name={fgdb_driver_name}')
      with CodeTimer(f'Write {file_gdb_dirname}', unit='s'):
        geodata.to_file(file_gdb_dirname, driver=fgdb_driver_name)

  
os.system(f'ls -alh {geojson_file}')
os.system(f'du -sh {file_gdb_dirname}')

