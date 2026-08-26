package propertycatalog

import (
	"reflect"
	"testing"
	"time"

	"github.com/twmb/franz-go/pkg/kgo"
)

func TestFranzProducerIsIdempotentAllISRAndHardBounded(t *testing.T) {
	producer, err := NewFranzProducer(FranzProducerConfig{
		Brokers: []string{"kafka:9092"}, Topic: "property-catalog-v1-dev",
		DeliveryTimeout: time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	defer producer.Close()
	writer, ok := producer.writer.(*franzRecordWriter)
	if !ok || writer.client == nil {
		t.Fatal("producer is not backed by the bounded Franz writer")
	}
	client := writer.client
	if !reflect.DeepEqual(client.OptValue(kgo.RequiredAcks), kgo.AllISRAcks()) ||
		client.OptValue(kgo.DisableIdempotentWrite) != false ||
		client.OptValue(kgo.MaxBufferedRecords) != int64(1) ||
		client.OptValue(kgo.MaxBufferedBytes) != int64(MaxRecordBytes) ||
		client.OptValue(kgo.RecordDeliveryTimeout) != time.Second {
		t.Fatalf(
			"unsafe producer options: acks=%T/%v disable_idempotence=%T/%v records=%T/%v bytes=%T/%v timeout=%T/%v",
			client.OptValue(kgo.RequiredAcks), client.OptValue(kgo.RequiredAcks),
			client.OptValue(kgo.DisableIdempotentWrite), client.OptValue(kgo.DisableIdempotentWrite),
			client.OptValue(kgo.MaxBufferedRecords), client.OptValue(kgo.MaxBufferedRecords),
			client.OptValue(kgo.MaxBufferedBytes), client.OptValue(kgo.MaxBufferedBytes),
			client.OptValue(kgo.RecordDeliveryTimeout), client.OptValue(kgo.RecordDeliveryTimeout),
		)
	}
}

func TestFranzConsumerIsManualCommitOneRecordAndMemoryBounded(t *testing.T) {
	validator, err := NewSequenceValidator(nil)
	if err != nil {
		t.Fatal(err)
	}
	consumer, err := NewFranzConsumer(FranzConsumerConfig{
		Brokers: []string{"kafka:9092"}, Topic: "property-catalog-v1-dev",
		GroupID: "property-catalog-v1-dev-consumer",
	}, &recordingHandler{}, validator)
	if err != nil {
		t.Fatal(err)
	}
	defer consumer.Close()
	source, ok := consumer.source.(*franzManualSource)
	if !ok || source.client == nil {
		t.Fatal("consumer is not backed by the manual Franz source")
	}
	client := source.client
	wantFetchBytes := int32(MaxRecordBytes + kafkaRecordOverheadAllowance)
	if client.OptValue(kgo.DisableAutoCommit) != true ||
		client.OptValue(kgo.BlockRebalanceOnPoll) != true ||
		client.OptValue(kgo.FetchIsolationLevel) != int8(1) ||
		client.OptValue(kgo.MaxConcurrentFetches) != 1 ||
		client.OptValue(kgo.FetchMaxBytes) != wantFetchBytes ||
		client.OptValue(kgo.FetchMaxPartitionBytes) != wantFetchBytes {
		t.Fatalf(
			"unsafe consumer options: auto=%v block=%v fetches=%v max=%v partition=%v",
			client.OptValue(kgo.DisableAutoCommit), client.OptValue(kgo.BlockRebalanceOnPoll),
			client.OptValue(kgo.MaxConcurrentFetches), client.OptValue(kgo.FetchMaxBytes),
			client.OptValue(kgo.FetchMaxPartitionBytes),
		)
	}
}

func TestFranzOrderedProducerUsesFixedTransactionalFence(t *testing.T) {
	producer, err := NewFranzProducer(FranzProducerConfig{
		Brokers: []string{"kafka:9092"}, Topic: "property-catalog-v1-dev",
		ClientID: "sequencer-output", DeliveryTimeout: time.Second,
		TransactionalID: "property-catalog-single-owner-v1", TransactionTimeout: 20 * time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	defer producer.Close()
	writer := producer.writer.(*franzRecordWriter)
	if !writer.transactional {
		t.Fatal("ordered output writer is not transactional")
	}
	transactionalValues := writer.client.OptValues(kgo.TransactionalID)
	if len(transactionalValues) != 2 || transactionalValues[1] != true {
		t.Fatalf("transactional values=%v", transactionalValues)
	}
	transactionalID, ok := transactionalValues[0].(*string)
	if !ok || transactionalID == nil || *transactionalID != "property-catalog-single-owner-v1" ||
		writer.client.OptValue(kgo.TransactionTimeout) != 20*time.Second {
		t.Fatalf("transactional ID=%v timeout=%v", transactionalValues[0], writer.client.OptValue(kgo.TransactionTimeout))
	}
}

func TestFranzCandidateProducerAndSourceAreBoundedAndStaticallyFenced(t *testing.T) {
	producer, err := NewFranzCandidateProducer(FranzProducerConfig{
		Brokers: []string{"kafka:9092"}, Topic: "property-candidates-v1-dev",
		ClientID: "candidate-producer", DeliveryTimeout: time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	defer producer.Close()
	writer := producer.writer.(*franzRecordWriter)
	if writer.transactional || writer.client.OptValue(kgo.MaxBufferedBytes) != int64(MaxCandidateRecordBytes) {
		t.Fatalf("candidate writer transactional=%v bytes=%v", writer.transactional, writer.client.OptValue(kgo.MaxBufferedBytes))
	}

	source, err := NewFranzCandidateSource(FranzCandidateSourceConfig{
		Brokers: []string{"kafka:9092"}, Topic: "property-candidates-v1-dev",
		GroupID: "property-candidate-sequencer", ClientID: "candidate-consumer",
		InstanceID: "property-catalog-singleton-v1",
	})
	if err != nil {
		t.Fatal(err)
	}
	defer source.Close()
	franzSource := source.(*franzManualSource)
	instanceValues := franzSource.client.OptValues(kgo.InstanceID)
	wantFetch := int32(MaxCandidateRecordBytes + kafkaRecordOverheadAllowance)
	if len(instanceValues) != 2 || instanceValues[0] != "property-catalog-singleton-v1" ||
		instanceValues[1] != true || franzSource.client.OptValue(kgo.DisableAutoCommit) != true ||
		franzSource.client.OptValue(kgo.BlockRebalanceOnPoll) != true ||
		franzSource.client.OptValue(kgo.FetchIsolationLevel) != int8(1) ||
		franzSource.client.OptValue(kgo.FetchMaxBytes) != wantFetch {
		t.Fatalf("unsafe candidate source instance=%v fetch=%v", instanceValues, franzSource.client.OptValue(kgo.FetchMaxBytes))
	}
}

func TestFranzCandidateSourceRejectsMissingFixedInstanceIdentity(t *testing.T) {
	err := ValidateFranzCandidateSourceConfig(FranzCandidateSourceConfig{
		Brokers: []string{"kafka:9092"}, Topic: "property-candidates-v1-dev",
		GroupID: "property-candidate-sequencer", ClientID: "candidate-consumer",
	})
	if err == nil {
		t.Fatal("candidate source accepted a dynamic process identity")
	}
}
