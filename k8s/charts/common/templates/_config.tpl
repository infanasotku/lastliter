{{- define "common.config" -}}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "common.fullname" . }}
data:
  ENV: {{ .Values.config.ENV | quote }}
  ADMIN__USERNAME: {{ .Values.config.ADMIN__USERNAME | quote }}
  REDIS__CLIENT: {{ .Values.config.REDIS__CLIENT | quote }}
  GDEBENZ__FINGERPRINT: {{ .Values.config.GDEBENZ__FINGERPRINT | quote }}
{{- end }}
