{{- define "common.job" -}}
apiVersion: batch/v1
kind: Job
metadata:
  name: {{ include "common.fullname" . }}-{{ .Values.container.tag | replace "." "-" | trunc 20 }}
spec:
  backoffLimit: 2
  ttlSecondsAfterFinished: 300
  template:
    spec:
      restartPolicy: OnFailure
      securityContext: {runAsNonRoot: true, runAsUser: 1000}
      containers:
        - name: {{ .Values.container.name }}
          image: {{ .Values.container.image }}:{{ .Values.container.tag }}
          imagePullPolicy: Always
          command: {{ .Values.container.command | toJson }}
          args: {{ .Values.container.args | toJson }}
          envFrom:
            - configMapRef: {name: {{ include "common.fullname" . }}}
            - secretRef: {name: {{ include "common.fullname" . }}}
          resources: {{ toYaml .Values.resources | nindent 12 }}
          securityContext:
            allowPrivilegeEscalation: false
            capabilities: {drop: [ALL]}
      imagePullSecrets: [{name: regcred}]
{{- end }}
