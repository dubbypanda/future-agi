package propertycatalog

import (
	"fmt"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func validRuntimeConfig(t *testing.T, workspaces ...string) RuntimeConfig {
	t.Helper()
	if len(workspaces) == 0 {
		workspaces = []string{testWorkspace}
	}
	return RuntimeConfig{
		Mode: RuntimeKafka, Environment: DevelopmentEnvironment,
		DevelopmentAcknowledgement: DevelopmentAcknowledgement,
		CatalogEpoch:               3, ProjectionVersion: 1, ProducerStreamID: testStream,
		WorkspaceAllowlist: workspaces,
		RevisionFenceFile:  filepath.Join(t.TempDir(), "revision-fence.json"),
		SpoolDirectory:     t.TempDir(),
		Kafka:              KafkaRuntimeConfig{Brokers: []string{"kafka:9092"}, Topic: "property-catalog-v1-dev"},
	}
}

func TestRuntimeConfigDefaultsDisabledAndEnabledModesRequireEnvironmentSpecificAcknowledgement(t *testing.T) {
	if mode, err := (RuntimeConfig{}).SelectedMode(); err != nil || mode != RuntimeDisabled {
		t.Fatalf("zero mode=%q err=%v", mode, err)
	}
	cfg := validRuntimeConfig(t)
	if mode, err := cfg.SelectedMode(); err != nil || mode != RuntimeKafka {
		t.Fatalf("mode=%q err=%v", mode, err)
	}
	defaults := cfg.WithDefaults()
	if defaults.QueueDepth != defaultQueueDepth ||
		defaults.ShutdownTimeout != defaultShutdownTimeout ||
		defaults.MaxChunkRows != defaultMaxChunkRows ||
		defaults.Kafka.DeliveryTimeout != DefaultDeliveryTransportTimeout ||
		defaults.Kafka.ClientID != "fi-collector-property-catalog-v1-dev" {
		t.Fatalf("defaults=%+v", defaults)
	}
	production := cfg
	production.Environment = ProductionEnvironment
	production.DevelopmentAcknowledgement = ""
	production.ProductionAcknowledgement = ProductionAcknowledgement
	if mode, err := production.SelectedMode(); err != nil || mode != RuntimeKafka {
		t.Fatalf("production mode=%q err=%v", mode, err)
	}
	if clientID := production.WithDefaults().Kafka.ClientID; clientID != "fi-collector-property-catalog-v1-prod" {
		t.Fatalf("production client ID=%q", clientID)
	}

	for name, mutate := range map[string]func(*RuntimeConfig){
		"production with dev acknowledgement": func(c *RuntimeConfig) { c.Environment = ProductionEnvironment },
		"both acknowledgements": func(c *RuntimeConfig) {
			c.ProductionAcknowledgement = ProductionAcknowledgement
		},
		"unknown environment":     func(c *RuntimeConfig) { c.Environment = "staging" },
		"missing acknowledgement": func(c *RuntimeConfig) { c.DevelopmentAcknowledgement = "" },
		"missing fence":           func(c *RuntimeConfig) { c.RevisionFenceFile = "" },
		"direct-like destination": func(c *RuntimeConfig) { c.Kafka.Brokers = nil },
		"delivery timeout above ceiling": func(c *RuntimeConfig) {
			c.Kafka.DeliveryTimeout = MaxDeliveryTimeout + time.Second
		},
		"shutdown timeout above ceiling": func(c *RuntimeConfig) {
			c.ShutdownTimeout = MaxShutdownTimeout + time.Second
		},
		"spool bytes above ceiling": func(c *RuntimeConfig) {
			c.MaxSpoolBytes = maxRuntimeSpoolBytes + 1
		},
		"unsorted allowlist": func(c *RuntimeConfig) {
			c.WorkspaceAllowlist = []string{"33333333-3333-4333-8333-333333333333", testWorkspace}
		},
	} {
		t.Run(name, func(t *testing.T) {
			candidate := cfg
			mutate(&candidate)
			if err := candidate.Validate(); err == nil {
				t.Fatal("unsafe runtime config was accepted")
			}
		})
	}
}

func TestRuntimeConfigRejectsUnknownModeWithoutNormalizingToEnabled(t *testing.T) {
	cfg := validRuntimeConfig(t)
	cfg.Mode = "prod"
	if err := cfg.Validate(); err == nil || !strings.Contains(err.Error(), "invalid runtime mode") {
		t.Fatalf("error=%v", err)
	}
}

func TestRuntimeConfigReportsReviewedWorkspaceAllowlistLimit(t *testing.T) {
	workspaces := make([]string, maxWorkspaceAllowlist+1)
	cfg := validRuntimeConfig(t, workspaces...)
	want := fmt.Sprintf("1..%d allowlisted workspaces", maxWorkspaceAllowlist)

	if err := cfg.Validate(); err == nil || !strings.Contains(err.Error(), want) {
		t.Fatalf("error=%v, want substring %q", err, want)
	}
}
