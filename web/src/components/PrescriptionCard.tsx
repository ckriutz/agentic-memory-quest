import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export interface Prescription {
  id?: string
  name: string
  dosage: string
  instructions: string
}

interface PrescriptionCardProps {
  prescriptions?: Prescription[]
}

export function PrescriptionCard({
  prescriptions = []
}: PrescriptionCardProps) {

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="text-2xl font-semibold text-gray-700">
          Prescriptions
        </CardTitle>
        <p className="text-sm text-gray-500 mt-1">Here are your current prescriptions</p>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* List of Prescriptions */}
        <div className="space-y-3">
          {prescriptions.length === 0 ? (
            <p className="text-gray-400 text-sm py-4">No prescriptions yet</p>
          ) : (
            prescriptions.map((prescription) => (
              <div
                key={prescription.id}
                className="border rounded-lg p-4 flex items-start gap-3 hover:bg-gray-50 transition"
              >
                <div className="text-2xl pt-1">💊</div>
                <div className="flex-1">
                  <div className="flex items-baseline gap-2">
                    <h3 className="text-lg font-semibold text-gray-800">
                      {prescription.name}
                    </h3>
                    <span className="text-gray-700 font-medium">
                      {prescription.dosage}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 mt-1">
                    {prescription.instructions}
                  </p>
                </div>
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  )
}
