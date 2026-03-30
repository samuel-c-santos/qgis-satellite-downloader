# Diagnóstico de Dependências CBERS-4A

## Script de Teste no Console Python do QGIS
Se o plugin mostrar que as ferramentas estão faltando, cole o código abaixo no **Console Python (Ctrl+Alt+P)** para identificar o erro real:

```python
import sys
import os
import site
import importlib
import traceback

print("--- DIAGNÓSTICO DE DEPENDÊNCIAS QGIS SATELLITE DOWNLOADER ---")
user_site = site.getusersitepackages()
if os.path.exists(user_site) and user_site not in sys.path:
    sys.path.insert(0, user_site)

dependencias = ['cbers4asat', 'geomet', 'geojson', 'rasterio', 'geopandas', 'shapely', 'skimage']

for dep in dependencias:
    try:
        mod = importlib.import_module(dep)
        print(f"✅ {dep.upper()}: ENCONTRADO em {mod.__file__}")
    except ImportError as e:
        print(f"❌ {dep.upper()}: NÃO ENCONTRADO (Erro: {e})")
    except Exception as e:
        print(f"⚠️ {dep.upper()}: ERRO AO CARREGAR (Erro: {traceback.format_exc()})")

print("-" * 40)
```

## Solução de Problemas Comuns
1. **Erro de DLL (Rasterio/Geopandas)**: Acontece quando o QGIS 3.44 e o 4.0 entram em conflito.
   - **Solução**: Reinicie o computador e use o botão "FORÇAR REINSTALAÇÃO" no plugin para garantir que as versões corretas sejam baixadas na pasta do perfil de usuário.
2. **Botão Laranja não some**: Certifique-se de **REINICIAR o QGIS** após a instalação bem-sucedida. O Python precisa atualizar a memória para "ver" os novos arquivos.
