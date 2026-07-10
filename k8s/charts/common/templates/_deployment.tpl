{{- define "common.deployment" -}}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "common.fullname" . }}
spec:
  replicas: {{ .Values.replicaCount | default 1 }}
  selector:
    matchLabels: {app: {{ include "common.fullname" . }}}
  template:
    metadata:
      labels:
        app: {{ include "common.fullname" . }}
        environment: {{ .Values.environment }}
      annotations:
        rollout/timestamp: {{ now | quote }}
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
      containers:
        - name: {{ .Values.container.name }}
          image: {{ .Values.container.image }}:{{ .Values.container.tag }}
          imagePullPolicy: Always
          command: {{ .Values.container.command | toJson }}
          args: {{ .Values.container.args | toJson }}
          {{- with .Values.container.port }}
          ports:
            - name: http
              containerPort: {{ . }}
          {{- end }}
          envFrom:
            - configMapRef: {name: {{ include "common.fullname" . }}}
            - secretRef: {name: {{ include "common.fullname" . }}}
          {{- with .Values.livenessProbe }}
          livenessProbe: {{ toYaml . | nindent 12 }}
          {{- end }}
          {{- with .Values.readinessProbe }}
          readinessProbe: {{ toYaml . | nindent 12 }}
          {{- end }}
          resources: {{ toYaml .Values.resources | nindent 12 }}
          securityContext:
            allowPrivilegeEscalation: false
            capabilities: {drop: [ALL]}
      imagePullSecrets: [{name: regcred}]
{{- end }}
