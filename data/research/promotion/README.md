# Evidencia de promoción

Los JSON de esta carpeta apuntan a datasets que no están versionados
(`data/BTC_1m_2025.csv` y similares, excluidos por `data/*` en `.gitignore`).
El `dataset_id` identifica los datos, pero el fichero no viaja con el repo: la
evidencia no se puede reproducir sin reconstruir el dataset desde Binance Vision
con el mismo símbolo, intervalo y rango.

Los informes no guardan el veredicto de las puertas (`gates: null`): el veredicto
vive en el ciclo de selección, no en la evidencia. Tampoco guardan las entradas
de la corrida (símbolo, intervalo, config, overrides); el workflow las adjunta en
un `meta.json` desde el cambio que acompaña a esta nota.

Antes de citar cualquier cifra de aquí, comprobar que el `config_hash` de la
evidencia coincide con el del perfil que va a operar.