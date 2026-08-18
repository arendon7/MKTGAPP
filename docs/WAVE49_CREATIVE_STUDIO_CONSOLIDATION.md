# Wave 49 · Creative Studio Consolidation

Wave 49 elimina la separación operativa entre el workspace técnico de edición y la biblioteca reusable de la empresa.

## Tres responsabilidades, sin duplicación

### ProjectStore
Sigue siendo el workspace de producción:
- fuentes importadas;
- proxies;
- timeline/composición;
- transcripción;
- renders y exports.

### CompanyMediaStore
Es la biblioteca reusable del producto:
- imágenes/videos finales o seleccionados;
- Campaigns (`media_ids`);
- Paid Media cuando el tipo de creativo está soportado;
- futuras superficies editoriales/distribución.

### CreativeBridgeStore
Solo guarda provenance:
- empresa;
- proyecto canónico de la empresa;
- tipo/id de fuente (`project_asset` o `render`);
- SHA-256 de la fuente;
- `company_media_id` resultante.

No almacena bytes multimedia.

## Promoción de renders

Solo un `RenderRecord` con:
- `status=PASS`;
- SHA-256 certificado;
- tamaño certificado;
- pertenencia al Marketing Studio de la empresa

puede promoverse.

Antes de copiar:
1. se recalculan SHA-256 y bytes del export;
2. cualquier drift bloquea la promoción;
3. se busca una promoción idéntica previa;
4. si ya existe, se verifica el archivo de biblioteca y se reutiliza;
5. si otra pieza de la misma empresa ya tiene el mismo SHA/kind, se reutilizan sus bytes y se crea un lineage adicional;
6. solo en caso contrario se incorpora el archivo a CompanyMediaStore.

Para renders se conservan width/height/duration en el media promovido.

## Promoción de project assets

Imágenes o videos fuente del Studio también pueden guardarse en biblioteca. Se verifica su archivo gestionado contra el SHA/tamaño registrado por ProjectStore antes de promover.

## Reutilización

Desde Creative Studio:
- `Guardar en biblioteca` promueve un output/fuente;
- `Usar en campaña` añade el `company_media_id` a la campaña de la misma empresa de forma idempotente;
- `Usar en Pauta` está disponible para imágenes y abre Paid Media con ese media preseleccionado;
- `Abrir Publicar` lleva al flujo editorial actual sin fingir todavía un binding automático de archivos sociales.

Video Ads no se simulan: el Paid Media Center actual sigue siendo image/link creative. Su soporte deberá añadirse como contrato propio antes de mostrar `Usar en Pauta` para video.

## Seguridad

- una empresa no puede promover outputs de otro workspace;
- una empresa no puede adjuntar media a campañas de otra empresa;
- renders FAIL/PENDING no son promovibles;
- drift SHA/bytes bloquea;
- no hay polling/background work;
- no se activa pauta;
- no se publica contenido automáticamente.

## Build

`build_full_mac_current.sh` incluye Wave 47 + Wave 48 + Wave 49 y ejecuta sus tres audits sobre el mismo `.app` arm64.
