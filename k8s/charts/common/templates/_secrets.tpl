{{- define "common.secrets" -}}
apiVersion: v1
kind: Secret
metadata:
  name: {{ include "common.fullname" . }}
type: Opaque
stringData:
{{- $secrets := (.Files.Get "temp-secrets.yaml" | required "missing decrypted secrets") | fromYaml }}
{{- range $key, $val := $secrets }}
  {{ $key }}: {{ $val | quote }}
{{- end }}
{{- end }}
