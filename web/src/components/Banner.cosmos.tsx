import { Card } from './ui/card'

export function Banner() {
  return (
    <Card className="w-full p-6 mb-6 bg-gradient-to-r from-orange-600 via-amber-500 to-yellow-500 text-white border-none shadow-lg">
      <div className="text-center">
        <h1 className="text-2xl font-bold mb-1">Welcome to the Contoso Resort and Spa!</h1>
        <p className="text-sm font-semibold opacity-95">🌌 Cosmos Edition — Powered by Azure Cosmos DB (DiskANN)</p>
        <p className="text-xs opacity-80 mt-1">Your intelligent assistant is ready to help make your experience unforgettable.</p>
      </div>
    </Card>
  )
}
