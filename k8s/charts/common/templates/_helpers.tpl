{{- define "common.fullname" -}}{{ .Release.Name | trunc 63 }}{{- end }}
