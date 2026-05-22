# nuclei wrapper — forces all data to D: drive
$env:NUCLEI_CONFIG_DIR = "D:\ai\tools\bin\nuclei-config"
$env:NUCLEI_TEMPLATES_PATH = "D:\ai\tools\bin\nuclei-templates"
$env:NUCLEI_CACHE_DIR = "D:\ai\tools\bin\nuclei-cache"

& "D:\ai\tools\bin\nuclei.exe" @args
