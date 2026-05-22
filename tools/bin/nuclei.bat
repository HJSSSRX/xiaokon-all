@echo off
rem nuclei wrapper — sets config/template/cache paths to D: drive
set NUCLEI_CONFIG_DIR=D:\ai\tools\bin\nuclei-config
set NUCLEI_TEMPLATES_PATH=D:\ai\tools\bin\nuclei-templates
D:\ai\tools\bin\nuclei.exe %*
