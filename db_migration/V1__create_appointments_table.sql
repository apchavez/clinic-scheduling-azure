CREATE TABLE appointments (
    appointment_id VARCHAR(50)  NOT NULL,
    insured_id     VARCHAR(20)  NOT NULL,
    schedule_id    INT          NOT NULL,
    status         VARCHAR(20)  NOT NULL,
    created_at     DATETIME2    NULL,
    completed_at   DATETIME2    NULL,
    CONSTRAINT PK_appointments PRIMARY KEY (appointment_id)
);
CREATE INDEX IX_appointments_insured_id ON appointments (insured_id);
