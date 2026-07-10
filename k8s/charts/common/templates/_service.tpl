{{- define "common.service" -}}
apiVersion: v1
kind: Service
metadata:
  name: {{ include "common.fullname" . }}
spec:
  selector: {app: {{ include "common.fullname" . }}}
  ports:
    - name: http
      port: {{ .Values.container.port }}
      targetPort: http
{{- end }}
