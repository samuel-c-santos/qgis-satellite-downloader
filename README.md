# QGIS Satellite Downloader (Plugin QGIS)

Plugin universal para download de imagens de satélite que combina dados globais do **Google Earth Engine** (Landsat/Sentinel) e dados nacionais de alta resolução do **INPE** (CBERS-4A).

## ⚠️ Segurança de Credenciais

> **IMPORTANTE**: Este projeto contém arquivos de configuração sensíveis que **NÃO** devem ser commitados. O arquivo `.gitignore` já ignora automaticamente:
> - `qgis_satellite_downloader/.env` (contém senhas e chaves)
> - `qgis_satellite_downloader/secrets/` (contém chaves JSON de contas de serviço)
>
> **Nunca compartilhe suas credenciais**. Cada usuário deve criar as suas próprias credenciais conforme descrito na documentação.

## Download (Recomendado)

Baixe a versão empacotada do plugin em **[Releases](https://github.com/samuel-c-santos/qgis-satellite-downloader/releases)** basta extrair, configurar as credenciais e usar.

## Documentação

| Guia | Descrição |
|------|------------|
| [COMO_INSTALAR.md](COMO_INSTALAR.md) | Passo a passo para instalar o plugin no QGIS |
| [CONFIGURACAO.md](CONFIGURACAO.md) | Como criar credenciais do Google Earth Engine e configurar o ambiente |

## 1. Estrutura do Projeto

- `qgis_satellite_downloader/`: Pasta do Plugin para QGIS 3.44+.
    - `scripts/`: Lógica de integração GEE e INPE STAC.
    - `secrets/`: Chaves JSON de Contas de Serviço (não versionado - configure as suas).
    - `.env`: Configurações de acesso (não versionado - configure as suas).
- `requirements.txt`: Dependências Python (cbers4asat, rasterio, geopandas, etc).

## 2. Configuração e Instalação

### 2.1 O Plugin do QGIS
1. Siga o guia completo em [COMO_INSTALAR.md](COMO_INSTALAR.md).
2. **Instalação Automática**: O plugin possui um botão interno ("FORÇAR REINSTALAÇÃO") que instala todas as dependências complexas (geopandas, rasterio) diretamente no QGIS, resolvendo conflitos de ambiente.

## 3. Funcionalidades de Elite

- **CBERS-4A (WPM 2m/8m)**: Acesso direto ao catálogo do INPE com download, composição RGBN e recorte automático por AOI.
- **Sentinel-2 & Landsat (GEE)**: Processamento em nuvem para séries históricas e mosaicos semestrais/mensais.
- **Reprojeção Automática**: O plugin detecta o sistema de coordenadas e converte a área de interesse (AOI) para o sistema nativo do satélite antes do recorte.
- **Buffer/Borda Flexível**: Aumente a área de interesse para visualizar o contexto da vizinhança.
- **Integração Visual**: Carregamento automático de GeoTIFFs no QGIS com reamostragem cúbica para melhor visualização.

## Licença

Este projeto está licenciado sob a **Licença MIT** - see the file [LICENSE](LICENSE) for details.

## 4. Desenvolvedor

**Samuel Santos**
- [LinkedIn](https://www.linkedin.com/in/samuelsantos-amb/)
- [GitHub](https://github.com/samuel-c-santos)
- [Site Pessoal](https://samuelsantos.site/)
